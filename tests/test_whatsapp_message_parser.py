"""
Offline tests for the Phase 2 WhatsApp message parsing layer in
src/adapters/whatsapp_message_parser.py: date/time resolution, the
06:00 Europe/London historical boundary (including midnight
rollover), deduplication identity, and final record building /
filtering. Pure functions only - no browser, no HTML, no network.
"""

from datetime import date, datetime, time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.whatsapp_message_parser import (
    LONDON_TZ,
    build_message_record,
    compute_historical_boundary,
    compute_message_id,
    is_before_historical_boundary,
    parse_clock_time,
    parse_pre_plain_text,
    resolve_date_separator,
)


# ==========================================================
# PRE-PLAIN-TEXT PARSING
# ==========================================================


def test_parse_pre_plain_text_with_sender_and_12_hour_time():
    result = parse_pre_plain_text("[9:15 am, 08/09/2026] Liam: ")

    assert result["time"] == time(9, 15)
    assert result["date"] == date(2026, 9, 8)
    assert result["sender"] == "Liam"


def test_parse_pre_plain_text_without_sender_for_direct_message():
    result = parse_pre_plain_text("[9:16 am, 08/09/2026] ")

    assert result["time"] == time(9, 16)
    assert result["date"] == date(2026, 9, 8)
    assert result["sender"] is None


def test_parse_pre_plain_text_returns_all_none_for_unrecognised_text():
    result = parse_pre_plain_text("not a pre-plain-text string")

    assert result == {"time": None, "date": None, "sender": None}


def test_parse_pre_plain_text_returns_all_none_for_empty_input():
    assert parse_pre_plain_text("") == {"time": None, "date": None, "sender": None}
    assert parse_pre_plain_text(None) == {"time": None, "date": None, "sender": None}


def test_parse_clock_time_handles_24_hour_and_12_hour_forms():
    assert parse_clock_time("09:15") == time(9, 15)
    assert parse_clock_time("9:15 am") == time(9, 15)
    assert parse_clock_time("9:15 PM") == time(21, 15)
    assert parse_clock_time("garbage") is None


# ==========================================================
# DATE SEPARATORS
# ==========================================================


def test_resolve_date_separator_today():
    reference = date(2026, 9, 8)

    assert resolve_date_separator("TODAY", reference) == date(2026, 9, 8)
    assert resolve_date_separator("today", reference) == date(2026, 9, 8)


def test_resolve_date_separator_yesterday():
    reference = date(2026, 9, 8)

    assert resolve_date_separator("YESTERDAY", reference) == date(2026, 9, 7)


def test_resolve_date_separator_explicit_date_format():
    reference = date(2026, 9, 8)

    assert resolve_date_separator("6 September 2026", reference) == date(2026, 9, 6)
    assert resolve_date_separator("01/09/2026", reference) == date(2026, 9, 1)


def test_resolve_date_separator_unrecognised_returns_none():
    assert resolve_date_separator("not a date", date(2026, 9, 8)) is None
    assert resolve_date_separator("", date(2026, 9, 8)) is None
    assert resolve_date_separator(None, date(2026, 9, 8)) is None


def test_resolve_date_separator_handles_yesterday_across_month_boundary():
    # 1 September's "yesterday" is 31 August - a real calendar
    # rollover, not just "subtract one from the day number".
    reference = date(2026, 9, 1)

    assert resolve_date_separator("YESTERDAY", reference) == date(2026, 8, 31)


# ==========================================================
# 06:00 HISTORICAL BOUNDARY (INCLUDING MIDNIGHT ROLLOVER)
# ==========================================================


def test_compute_historical_boundary_is_six_am_london_today():
    now_london = datetime(2026, 9, 8, 14, 30, tzinfo=LONDON_TZ)

    boundary = compute_historical_boundary(now_london)

    assert boundary == datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)


def test_message_just_before_boundary_is_before():
    boundary = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)
    message_datetime = datetime(2026, 9, 8, 5, 59, tzinfo=LONDON_TZ)

    assert is_before_historical_boundary(message_datetime, boundary) is True


def test_message_exactly_at_boundary_is_not_before():
    boundary = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)
    message_datetime = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)

    assert is_before_historical_boundary(message_datetime, boundary) is False


def test_message_just_after_boundary_is_not_before():
    boundary = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)
    message_datetime = datetime(2026, 9, 8, 6, 1, tzinfo=LONDON_TZ)

    assert is_before_historical_boundary(message_datetime, boundary) is False


def test_yesterday_late_night_message_is_before_todays_boundary():
    # A message sent at 23:58 the calendar day before "today" must be
    # treated as before today's 06:00 boundary, even though 23:58 is
    # numerically "later" than 06:00 - the date matters, not just the
    # clock time.
    boundary = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)
    message_datetime = datetime(2026, 9, 7, 23, 58, tzinfo=LONDON_TZ)

    assert is_before_historical_boundary(message_datetime, boundary) is True


def test_today_just_after_midnight_message_is_before_boundary():
    # A message sent at 00:15 today (just after midnight, still well
    # before 06:00) must correctly compare as before the boundary.
    boundary = datetime(2026, 9, 8, 6, 0, tzinfo=LONDON_TZ)
    message_datetime = datetime(2026, 9, 8, 0, 15, tzinfo=LONDON_TZ)

    assert is_before_historical_boundary(message_datetime, boundary) is True


# ==========================================================
# MESSAGE IDENTITY / DEDUPLICATION
# ==========================================================


def test_compute_message_id_uses_native_id_when_available():
    message_id, source = compute_message_id(
        "true_123@g.us_ABC",
        "Rovema production line 1",
        "Liam",
        datetime(2026, 9, 8, 9, 15, tzinfo=LONDON_TZ),
        "Line stopped",
    )

    assert message_id == "true_123@g.us_ABC"
    assert source == "native"


def test_compute_message_id_derives_deterministic_hash_without_native_id():
    args = (
        None,
        "Rovema production line 1",
        "Liam",
        datetime(2026, 9, 8, 9, 15, tzinfo=LONDON_TZ),
        "Line stopped",
    )

    first_id, first_source = compute_message_id(*args)
    second_id, second_source = compute_message_id(*args)

    assert first_id == second_id
    assert first_source == "derived_hash"
    assert second_source == "derived_hash"
    assert len(first_id) == 64  # sha256 hex digest


def test_compute_message_id_hash_differs_for_different_text():
    base_args = (
        None,
        "Rovema production line 1",
        "Liam",
        datetime(2026, 9, 8, 9, 15, tzinfo=LONDON_TZ),
    )

    id_one, _ = compute_message_id(*base_args, "Line stopped")
    id_two, _ = compute_message_id(*base_args, "Line running again")

    assert id_one != id_two


# ==========================================================
# RECORD BUILDING / FILTERING
# ==========================================================


def _raw_message(
    text="Line stopped, need engineer",
    sender="Liam",
    is_outgoing=False,
    time_str="9:15 am",
    date_str="08/09/2026",
    raw_id="false_123@g.us_ABC",
    is_edited=False,
    is_deleted_placeholder=False,
    has_media=False,
):
    pre_plain_text = (
        f"[{time_str}, {date_str}] {sender}: "
        if sender
        else f"[{time_str}, {date_str}] "
    )
    return {
        "kind": "message",
        "raw_id": raw_id,
        "is_outgoing": is_outgoing,
        "pre_plain_text": pre_plain_text,
        "text": text,
        "is_deleted_placeholder": is_deleted_placeholder,
        "has_media": has_media,
        "is_edited": is_edited,
    }


def test_build_message_record_for_incoming_message():
    record = build_message_record(
        _raw_message(), "Rovema production line 1", date_context=None
    )

    assert record["message_id"] == "false_123@g.us_ABC"
    assert record["message_id_source"] == "native"
    assert record["group_name"] == "Rovema production line 1"
    assert record["sender_name"] == "Liam"
    assert record["message_text"] == "Line stopped, need engineer"
    assert record["is_outgoing"] is False
    assert record["is_edited"] is False
    assert record["message_timestamp"] == "2026-09-08T09:15:00+01:00"
    assert "extracted_at" in record


def test_build_message_record_for_outgoing_message_defaults_sender_to_you():
    raw = _raw_message(sender=None, is_outgoing=True, text="On it now")

    record = build_message_record(raw, "Rovema production line 1", date_context=None)

    assert record["is_outgoing"] is True
    assert record["sender_name"] == "You"


def test_build_message_record_marks_edited():
    raw = _raw_message(is_edited=True)

    record = build_message_record(raw, "Rovema production line 1", date_context=None)

    assert record["is_edited"] is True


def test_build_message_record_uses_date_context_over_embedded_date():
    # date_context comes from the most recent date separator and takes
    # priority over the date embedded in pre-plain-text.
    raw = _raw_message(date_str="01/01/2020")

    record = build_message_record(
        raw, "Rovema production line 1", date_context=date(2026, 9, 8)
    )

    assert record["message_timestamp"].startswith("2026-09-08")


def test_build_message_record_returns_none_for_deleted_placeholder():
    raw = _raw_message(text="This message was deleted", is_deleted_placeholder=True)

    assert build_message_record(raw, "Rovema production line 1", None) is None


def test_build_message_record_returns_none_for_media_only_message():
    raw = _raw_message(text=None, has_media=True)

    assert build_message_record(raw, "Rovema production line 1", None) is None


def test_build_message_record_keeps_media_message_with_caption():
    raw = _raw_message(text="See photo of the fault", has_media=True)

    record = build_message_record(raw, "Rovema production line 1", None)

    assert record is not None
    assert record["message_text"] == "See photo of the fault"


def test_build_message_record_returns_none_for_empty_text():
    raw = _raw_message(text="   ")

    assert build_message_record(raw, "Rovema production line 1", None) is None


def test_build_message_record_returns_none_for_non_message_kind():
    raw = {
        "kind": "system",
        "raw_id": None,
        "is_outgoing": None,
        "pre_plain_text": None,
        "text": None,
        "is_deleted_placeholder": False,
        "has_media": False,
        "is_edited": False,
    }

    assert build_message_record(raw, "Rovema production line 1", None) is None


def test_build_message_record_returns_none_when_time_unresolvable():
    raw = _raw_message()
    raw["pre_plain_text"] = "not parseable metadata"

    assert (
        build_message_record(raw, "Rovema production line 1", date_context=None)
        is None
    )
