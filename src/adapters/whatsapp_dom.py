# ==========================================================
# TONNAGEFLOW PULSE
# WhatsApp Web DOM Extraction Layer - Phase 2
# ==========================================================
#
# This module turns one WhatsApp Web element's raw outer HTML into a
# plain, framework-agnostic dict of extracted strings/flags. It never
# interprets dates or times, never decides whether a message should be
# kept, and never writes anything to disk - that happens in
# whatsapp_message_parser.py and whatsapp_message_store.py, so a future
# capture mechanism (e.g. a tablet UI) can replace only this file and
# reuse the rest of the pipeline unchanged.
#
# WhatsApp Web's DOM is unofficial, undocumented, and changes without
# notice. Every lookup here tries a short, explicit, most-specific-first
# list of selectors and returns None/False rather than raising when
# nothing matches, so one unrecognised row never crashes a whole
# extraction run. Selectors will likely need adjustment after the first
# controlled live test and after any WhatsApp Web UI update - see the
# module docstring in whatsapp_web_observer.py.

from bs4 import BeautifulSoup

DELETED_MESSAGE_TEXT = "this message was deleted"

# Ordered, most-specific-first. The first selector that matches wins.
CHAT_TITLE_SELECTORS = [
    {"data-testid": "conversation-info-header-chat-title"},
    {"data-testid": "conversation-title"},
]

DATE_SEPARATOR_SELECTORS = [
    {"data-testid": "conversation-date-separator"},
]

EDITED_MARKER_SELECTORS = [
    {"data-testid": "msg-edited"},
]

REACTION_SELECTORS = [
    {"data-testid": "reactions"},
    {"data-testid": "reaction-container"},
]

SYSTEM_ROW_SELECTORS = [
    {"data-testid": "msg-system"},
]

MEDIA_SELECTORS = [
    {"data-testid": "media-content"},
]


def _first_match(soup, selectors):
    for attrs in selectors:
        found = soup.find(attrs=attrs)
        if found is not None:
            return found
    return None


def _find_text_container(soup):
    text_container = soup.find(
        "span",
        attrs={"class": lambda value: bool(value) and "selectable-text" in value},
    )

    if text_container is None:
        text_container = soup.find(attrs={"data-testid": "conversation-text"})

    return text_container


# ==========================================================
# CHAT HEADER
# ==========================================================


def extract_chat_title(header_html):
    """Extract the currently open chat's title text from header HTML."""
    if not header_html:
        return None

    soup = BeautifulSoup(header_html, "html.parser")
    element = _first_match(soup, CHAT_TITLE_SELECTORS)

    if element is None:
        # Fallback: WhatsApp Web commonly puts the full chat title in a
        # "title" attribute (for text overflow tooltips) on the header.
        element = soup.find(attrs={"title": True})

    if element is None:
        return None

    text = element.get("title") or element.get_text(strip=True)
    text = text.strip() if text else None
    return text or None


# ==========================================================
# DATE SEPARATORS
# ==========================================================


def extract_date_separator_text(row_html):
    """
    Return a date-separator row's visible text (e.g. "TODAY",
    "YESTERDAY", or a displayed date), or None if this row is not a
    date separator.
    """
    if not row_html:
        return None

    soup = BeautifulSoup(row_html, "html.parser")
    element = _first_match(soup, DATE_SEPARATOR_SELECTORS)

    if element is None:
        return None

    text = element.get_text(strip=True)
    return text or None


# ==========================================================
# MESSAGE ROWS
# ==========================================================


def classify_and_extract_row(row_html):
    """
    Classify one message-row's HTML and extract its raw fields.

    Returns a dict:
        {
            "kind": "message" | "system" | "reaction" | "unknown",
            "raw_id": str | None,
            "is_outgoing": bool | None,
            "pre_plain_text": str | None,
            "text": str | None,
            "is_deleted_placeholder": bool,
            "has_media": bool,
            "is_edited": bool,
        }

    Never raises on malformed/unexpected HTML - returns
    kind="unknown" with everything else None/False instead, so
    callers can safely skip it.
    """
    result = {
        "kind": "unknown",
        "raw_id": None,
        "is_outgoing": None,
        "pre_plain_text": None,
        "text": None,
        "is_deleted_placeholder": False,
        "has_media": False,
        "is_edited": False,
    }

    if not row_html:
        return result

    try:
        soup = BeautifulSoup(row_html, "html.parser")
    except Exception:
        return result

    root = soup.find(True)
    if root is None:
        return result

    if _first_match(soup, SYSTEM_ROW_SELECTORS) is not None:
        result["kind"] = "system"
        return result

    if _first_match(soup, REACTION_SELECTORS) is not None:
        result["kind"] = "reaction"
        return result

    classes = root.get("class") or []

    is_outgoing = None
    if "message-out" in classes:
        is_outgoing = True
    elif "message-in" in classes:
        is_outgoing = False

    data_id = root.get("data-id")

    pre_plain_element = soup.find(attrs={"data-pre-plain-text": True})
    pre_plain_text = (
        pre_plain_element.get("data-pre-plain-text")
        if pre_plain_element is not None
        else None
    )

    text_container = _find_text_container(soup)
    text = text_container.get_text(" ", strip=True) if text_container else None

    has_media = _first_match(soup, MEDIA_SELECTORS) is not None or bool(
        soup.find("img") or soup.find("video")
    )

    is_deleted_placeholder = bool(
        text and DELETED_MESSAGE_TEXT in text.strip().lower()
    )

    is_edited = _first_match(soup, EDITED_MARKER_SELECTORS) is not None

    looks_like_message = bool(data_id or pre_plain_text or text or has_media)

    if not looks_like_message:
        result["kind"] = "unknown"
        return result

    result.update(
        {
            "kind": "message",
            "raw_id": data_id,
            "is_outgoing": is_outgoing,
            "pre_plain_text": pre_plain_text,
            "text": text,
            "is_deleted_placeholder": is_deleted_placeholder,
            "has_media": has_media,
            "is_edited": is_edited,
        }
    )
    return result
