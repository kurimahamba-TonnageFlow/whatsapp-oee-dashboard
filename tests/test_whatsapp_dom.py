"""
Offline tests for the Phase 2 WhatsApp Web DOM extraction layer in
src/adapters/whatsapp_dom.py, using only hand-written synthetic HTML
fixtures. Never accesses live WhatsApp Web.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.whatsapp_dom import (
    classify_and_extract_row,
    extract_chat_title,
    extract_date_separator_text,
)


# ==========================================================
# CHAT TITLE
# ==========================================================


def test_extract_chat_title_from_testid_selector():
    header_html = (
        '<header><span data-testid="conversation-info-header-chat-title">'
        "Rovema production line 1</span></header>"
    )

    assert extract_chat_title(header_html) == "Rovema production line 1"


def test_extract_chat_title_falls_back_to_title_attribute():
    header_html = '<header><span title="Rovema production line 1">Rov...</span></header>'

    assert extract_chat_title(header_html) == "Rovema production line 1"


def test_extract_chat_title_returns_none_when_missing():
    assert extract_chat_title("<header></header>") is None
    assert extract_chat_title("") is None
    assert extract_chat_title(None) is None


# ==========================================================
# DATE SEPARATORS
# ==========================================================


def test_extract_date_separator_text_today():
    row_html = (
        '<div data-testid="conversation-date-separator">'
        "<span>TODAY</span></div>"
    )

    assert extract_date_separator_text(row_html) == "TODAY"


def test_extract_date_separator_text_explicit_date():
    row_html = (
        '<div data-testid="conversation-date-separator">'
        "<span>6 September 2026</span></div>"
    )

    assert extract_date_separator_text(row_html) == "6 September 2026"


def test_extract_date_separator_text_returns_none_for_non_separator_row():
    row_html = '<div class="message-in" data-id="abc"><span>Hello</span></div>'

    assert extract_date_separator_text(row_html) is None


# ==========================================================
# MESSAGE ROWS - INCOMING / OUTGOING / TEXT / TIME
# ==========================================================


def _incoming_row(text="Line stopped, need engineer", sender="Liam", time_str="9:15 am", date_str="08/09/2026", data_id="false_123@g.us_ABC"):
    return f'''
    <div class="message-in" data-id="{data_id}" role="row">
      <div class="copyable-text" data-pre-plain-text="[{time_str}, {date_str}] {sender}: ">
        <span class="selectable-text copyable-text"><span>{text}</span></span>
      </div>
    </div>
    '''


def _outgoing_row(text="On it now", time_str="9:16 am", date_str="08/09/2026", data_id="true_123@g.us_DEF"):
    return f'''
    <div class="message-out" data-id="{data_id}" role="row">
      <div class="copyable-text" data-pre-plain-text="[{time_str}, {date_str}] ">
        <span class="selectable-text copyable-text"><span>{text}</span></span>
      </div>
    </div>
    '''


def test_classify_incoming_message_extracts_sender_time_and_text():
    result = classify_and_extract_row(_incoming_row())

    assert result["kind"] == "message"
    assert result["is_outgoing"] is False
    assert result["text"] == "Line stopped, need engineer"
    assert result["pre_plain_text"] == "[9:15 am, 08/09/2026] Liam: "
    assert result["raw_id"] == "false_123@g.us_ABC"
    assert result["is_edited"] is False
    assert result["has_media"] is False


def test_classify_outgoing_message_marks_is_outgoing_true():
    result = classify_and_extract_row(_outgoing_row())

    assert result["kind"] == "message"
    assert result["is_outgoing"] is True
    assert result["text"] == "On it now"


def test_classify_edited_message_sets_is_edited_true():
    row_html = f'''
    <div class="message-in" data-id="false_123@g.us_GHI" role="row">
      <div class="copyable-text" data-pre-plain-text="[9:20 am, 08/09/2026] Liam: ">
        <span class="selectable-text copyable-text"><span>Fixed now</span></span>
      </div>
      <span data-testid="msg-edited">Edited</span>
    </div>
    '''

    result = classify_and_extract_row(row_html)

    assert result["kind"] == "message"
    assert result["is_edited"] is True


def test_classify_deleted_placeholder_is_flagged():
    row_html = f'''
    <div class="message-in" data-id="false_123@g.us_JKL" role="row">
      <div class="copyable-text" data-pre-plain-text="[9:21 am, 08/09/2026] Liam: ">
        <span class="selectable-text copyable-text"><span>This message was deleted</span></span>
      </div>
    </div>
    '''

    result = classify_and_extract_row(row_html)

    assert result["kind"] == "message"
    assert result["is_deleted_placeholder"] is True


def test_classify_reaction_row_is_ignored_kind():
    row_html = '<div data-testid="reactions"><span>\U0001F44D</span></div>'

    result = classify_and_extract_row(row_html)

    assert result["kind"] == "reaction"


def test_classify_system_row_is_ignored_kind():
    row_html = (
        '<div data-testid="msg-system"><span>'
        "Messages are end-to-end encrypted.</span></div>"
    )

    result = classify_and_extract_row(row_html)

    assert result["kind"] == "system"


def test_classify_media_only_message_has_media_true_and_no_text():
    row_html = '''
    <div class="message-in" data-id="false_123@g.us_MNO" role="row">
      <div data-testid="media-content"><img src="blob:whatsapp/x" /></div>
    </div>
    '''

    result = classify_and_extract_row(row_html)

    assert result["kind"] == "message"
    assert result["has_media"] is True
    assert result["text"] is None


# ==========================================================
# MALFORMED / EMPTY INPUT
# ==========================================================


def test_classify_empty_html_returns_unknown_without_raising():
    result = classify_and_extract_row("")

    assert result["kind"] == "unknown"
    assert result["text"] is None


def test_classify_none_returns_unknown_without_raising():
    result = classify_and_extract_row(None)

    assert result["kind"] == "unknown"


def test_classify_malformed_html_does_not_raise():
    result = classify_and_extract_row("<div class='message-in'><span>unterminated")

    assert result["kind"] in ("message", "unknown")


def test_classify_row_with_no_recognisable_content_is_unknown():
    result = classify_and_extract_row("<div><span>just some layout element</span></div>")

    assert result["kind"] == "unknown"
