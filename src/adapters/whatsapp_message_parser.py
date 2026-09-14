# ==========================================================
# TONNAGEFLOW PULSE
# WhatsApp Web Message Parsing Layer - Phase 2
# ==========================================================
#
# Pure functions that turn the raw, framework-agnostic dicts produced
# by whatsapp_dom.py into final message records, or decide to drop
# them (system notices, reactions, deleted placeholders, media-only
# messages, messages with no usable text or unparseable date/time).
#
# Nothing here touches Playwright, BeautifulSoup, or disk. That keeps
# this module trivially testable with plain strings/dicts, and keeps
# it reusable behind a different capture mechanism later (see the
# module docstring in whatsapp_web_observer.py).

import hashlib
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")
HISTORICAL_BOUNDARY_HOUR = 6

_PRE_PLAIN_TEXT_PATTERN = re.compile(
    r"^\[(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm])?),\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\]\s*(?P<sender>[^:]*):?\s*$"
)

_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y")
_SEPARATOR_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d %B %Y",
    "%B %d, %Y",
    "%A, %B %d, %Y",
)
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p")


# ==========================================================
# TIME / DATE PARSING
# ==========================================================


def parse_clock_time(text):
    """Parse a bare clock-time string (e.g. "9:15", "9:15 am") into a time."""
    if not text:
        return None

    normalised = text.strip().upper()

    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(normalised, fmt).time()
        except ValueError:
            continue

    return None


def parse_pre_plain_text(text):
    """
    Parse WhatsApp's data-pre-plain-text metadata, e.g.
    "[9:15 am, 08/09/2026] John Doe: " into its time/date/sender parts.

    Returns {"time": time|None, "date": date|None, "sender": str|None} -
    all None if the text does not match a recognised shape.
    """
    empty = {"time": None, "date": None, "sender": None}

    if not text:
        return empty

    match = _PRE_PLAIN_TEXT_PATTERN.match(text.strip())
    if not match:
        return empty

    parsed_time = parse_clock_time(match.group("time"))

    parsed_date = None
    raw_date = match.group("date")
    for fmt in _DATE_FORMATS:
        try:
            parsed_date = datetime.strptime(raw_date, fmt).date()
            break
        except ValueError:
            continue

    sender = match.group("sender").strip() or None

    return {"time": parsed_time, "date": parsed_date, "sender": sender}


def resolve_date_separator(text, reference_date):
    """
    Resolve a WhatsApp date-separator's visible text into a calendar
    date, given the Europe/London date the observer considers "today".

    Recognises "TODAY" and "YESTERDAY" (case-insensitive) plus a small
    set of explicit date formats. Returns None if unrecognised.
    """
    if not text:
        return None

    normalised = text.strip().upper()

    if normalised == "TODAY":
        return reference_date

    if normalised == "YESTERDAY":
        return reference_date - timedelta(days=1)

    for fmt in _SEPARATOR_DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue

    return None


def compute_historical_boundary(now_london):
    """
    Return the tz-aware Europe/London datetime for 06:00 on
    now_london's calendar date - the point before which scrolling
    should stop.
    """
    return datetime.combine(
        now_london.date(),
        time(HISTORICAL_BOUNDARY_HOUR, 0),
        tzinfo=LONDON_TZ,
    )


def is_before_historical_boundary(message_datetime, boundary):
    """True if message_datetime is strictly earlier than the boundary."""
    return message_datetime < boundary


# ==========================================================
# MESSAGE IDENTITY / DEDUPLICATION
# ==========================================================


def compute_message_id(raw_id, group_name, sender_name, message_datetime, text):
    """
    Return (message_id, source). Uses the stable WhatsApp id when
    available; otherwise a deterministic sha256 hash of group, sender,
    timestamp, and text, so the same message always dedupes to the
    same key even without a native id.
    """
    if raw_id:
        return raw_id, "native"

    basis = "|".join(
        [
            group_name or "",
            sender_name or "",
            message_datetime.isoformat() if message_datetime else "",
            text or "",
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return digest, "derived_hash"


# ==========================================================
# RECORD BUILDING
# ==========================================================


def resolve_message_datetime(raw_row, date_context):
    """
    Resolve a raw row's Europe/London timestamp from its
    data-pre-plain-text metadata and/or the current date_context
    (the calendar date established by the most recent date separator
    seen while scrolling). Returns None if either the date or the
    time cannot be determined. Used both to decide whether scrolling
    has passed the historical boundary and inside build_message_record
    - kept separate so boundary-checking does not depend on whether a
    row is otherwise kept or ignored.
    """
    pre_plain = parse_pre_plain_text(raw_row.get("pre_plain_text"))

    message_date = date_context or pre_plain["date"]
    message_time = pre_plain["time"]

    if message_date is None or message_time is None:
        return None

    return datetime.combine(message_date, message_time, tzinfo=LONDON_TZ)


def build_message_record(raw_row, group_name, date_context, extracted_at=None):
    """
    Turn one whatsapp_dom.classify_and_extract_row() result into a
    final message record, or None if it should be ignored: a system
    notice, a reaction, a deleted-message placeholder, a message with
    no usable text (including media-only messages, which have no
    caption text), or a message whose date/time cannot be resolved.

    date_context is the calendar date established by the most recent
    date separator seen while scrolling (a Europe/London date, or
    None if none has been seen yet).
    """
    if raw_row.get("kind") != "message":
        return None

    if raw_row.get("is_deleted_placeholder"):
        return None

    text = raw_row.get("text")
    if not text or not text.strip():
        # Covers media-only messages (no caption) as well as any other
        # row with nothing usable to record.
        return None

    message_datetime = resolve_message_datetime(raw_row, date_context)
    if message_datetime is None:
        return None

    pre_plain = parse_pre_plain_text(raw_row.get("pre_plain_text"))
    sender_name = pre_plain["sender"]
    is_outgoing = bool(raw_row.get("is_outgoing"))

    if is_outgoing and not sender_name:
        sender_name = "You"

    message_id, message_id_source = compute_message_id(
        raw_row.get("raw_id"),
        group_name,
        sender_name,
        message_datetime,
        text,
    )

    extracted_at = extracted_at or datetime.now(LONDON_TZ)

    return {
        "message_id": message_id,
        "message_id_source": message_id_source,
        "group_name": group_name,
        "sender_name": sender_name,
        "message_timestamp": message_datetime.isoformat(),
        "message_text": text,
        "is_outgoing": is_outgoing,
        "is_edited": bool(raw_row.get("is_edited")),
        "extracted_at": extracted_at.isoformat(),
    }
