"""
Offline tests for the Phase 2 WhatsApp message persistence layer in
src/adapters/whatsapp_message_store.py: JSONL append-only writing,
deduplication (native id and derived-hash id), dedup-state recovery,
and resilience to a missing/corrupted state file. Uses tmp_path only -
never touches the real .pulse_shadow_inbox/ directory or live data.
"""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.whatsapp_message_store import WhatsAppMessageStore


def _record(message_id="id-1", text="Line stopped"):
    return {
        "message_id": message_id,
        "message_id_source": "native",
        "group_name": "Rovema production line 1",
        "sender_name": "Liam",
        "message_timestamp": "2026-09-08T09:15:00+01:00",
        "message_text": text,
        "is_outgoing": False,
        "is_edited": False,
        "extracted_at": "2026-09-08T09:16:00+01:00",
    }


def _read_lines(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_append_message_writes_one_jsonl_line(tmp_path):
    store = WhatsAppMessageStore(tmp_path)

    appended = store.append_message(_record())

    assert appended is True
    lines = _read_lines(store.messages_path)
    assert len(lines) == 1
    assert lines[0]["message_id"] == "id-1"


def test_append_message_is_utf8(tmp_path):
    store = WhatsAppMessageStore(tmp_path)
    store.append_message(_record(text="cafe line deja down - éè"))

    raw_bytes = store.messages_path.read_bytes()
    decoded = raw_bytes.decode("utf-8")
    assert "éè" in decoded


def test_duplicate_message_id_is_not_appended_twice(tmp_path):
    store = WhatsAppMessageStore(tmp_path)

    first = store.append_message(_record(message_id="dup-1"))
    second = store.append_message(_record(message_id="dup-1"))

    assert first is True
    assert second is False
    assert len(_read_lines(store.messages_path)) == 1


def test_new_store_instance_recognises_previously_seen_id_via_dedup_state(tmp_path):
    store_one = WhatsAppMessageStore(tmp_path)
    store_one.append_message(_record(message_id="persisted-1"))

    store_two = WhatsAppMessageStore(tmp_path)

    assert store_two.is_known("persisted-1") is True
    assert store_two.append_message(_record(message_id="persisted-1")) is False


def test_dedup_state_file_is_created_and_valid_json(tmp_path):
    store = WhatsAppMessageStore(tmp_path)
    store.append_message(_record(message_id="state-1"))

    assert store.dedup_state_path.exists()
    stored_ids = json.loads(store.dedup_state_path.read_text(encoding="utf-8"))
    assert "state-1" in stored_ids


def test_missing_dedup_state_file_is_rebuilt_from_jsonl(tmp_path):
    store_one = WhatsAppMessageStore(tmp_path)
    store_one.append_message(_record(message_id="rebuild-1"))

    store_one.dedup_state_path.unlink()

    store_two = WhatsAppMessageStore(tmp_path)

    assert store_two.is_known("rebuild-1") is True


def test_corrupted_dedup_state_file_does_not_crash_and_falls_back_to_jsonl(tmp_path):
    store_one = WhatsAppMessageStore(tmp_path)
    store_one.append_message(_record(message_id="corrupt-1"))

    store_one.dedup_state_path.write_text("{ not valid json", encoding="utf-8")

    store_two = WhatsAppMessageStore(tmp_path)

    assert store_two.is_known("corrupt-1") is True


def test_append_does_not_overwrite_existing_records_across_sessions(tmp_path):
    store_one = WhatsAppMessageStore(tmp_path)
    store_one.append_message(_record(message_id="first"))

    store_two = WhatsAppMessageStore(tmp_path)
    store_two.append_message(_record(message_id="second"))

    lines = _read_lines(tmp_path / "whatsapp_messages.jsonl")
    ids = [line["message_id"] for line in lines]

    assert ids == ["first", "second"]


def test_known_id_count_reflects_appended_messages(tmp_path):
    store = WhatsAppMessageStore(tmp_path)

    assert store.known_id_count() == 0

    store.append_message(_record(message_id="a"))
    store.append_message(_record(message_id="b"))
    store.append_message(_record(message_id="a"))  # duplicate

    assert store.known_id_count() == 2
