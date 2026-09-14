# ==========================================================
# TONNAGEFLOW PULSE
# WhatsApp Web Message Persistence Layer - Phase 2
# ==========================================================
#
# Append-only JSON Lines storage with a separate, on-disk
# deduplication state. Deals only with plain dicts and file paths, so
# it can be reused unchanged by a future capture mechanism (see the
# module docstring in whatsapp_web_observer.py).
#
# Safety: the JSONL file is only ever appended to, one already-built
# line at a time, and flushed and fsynced immediately after each
# write. A failure anywhere else in the pipeline (DOM extraction,
# parsing, scrolling) can never truncate or corrupt lines already
# written here. The dedup-state file is rewritten with a write-then-
# atomic-replace so a crash mid-write leaves either the old or the
# new version intact, never a half-written file - and even if that
# file is lost entirely, known ids are rebuilt from the JSONL itself.

import json
import os
from pathlib import Path

MESSAGES_FILENAME = "whatsapp_messages.jsonl"
DEDUP_STATE_FILENAME = "dedup_state.json"


class WhatsAppMessageStore:
    def __init__(self, inbox_dir: Path):
        self.inbox_dir = Path(inbox_dir)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        self.messages_path = self.inbox_dir / MESSAGES_FILENAME
        self.dedup_state_path = self.inbox_dir / DEDUP_STATE_FILENAME

        self._known_ids = self._load_known_ids()

    def _load_known_ids(self):
        known_ids = set()

        if self.dedup_state_path.exists():
            try:
                stored = json.loads(self.dedup_state_path.read_text(encoding="utf-8"))
                if isinstance(stored, list):
                    known_ids.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

        if self.messages_path.exists():
            try:
                with self.messages_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message_id = record.get("message_id")
                        if message_id:
                            known_ids.add(message_id)
            except OSError:
                pass

        return known_ids

    def is_known(self, message_id):
        return message_id in self._known_ids

    def append_message(self, record):
        """
        Append one record if its message_id has not been seen before.
        Returns True if it was appended, False if it was a duplicate.
        """
        message_id = record.get("message_id")

        if message_id and message_id in self._known_ids:
            return False

        line = json.dumps(record, ensure_ascii=False)

        with self.messages_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        if message_id:
            self._known_ids.add(message_id)
            self._persist_dedup_state()

        return True

    def _persist_dedup_state(self):
        temp_path = self.dedup_state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(sorted(self._known_ids)), encoding="utf-8")
        os.replace(temp_path, self.dedup_state_path)

    def known_id_count(self):
        return len(self._known_ids)
