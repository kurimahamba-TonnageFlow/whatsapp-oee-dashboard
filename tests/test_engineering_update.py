"""
Offline test for src.database.save_engineering_update (the CLI-era
write path used by src/main.py's capture_engineering_update, not the
Stage 5A HTTP API's add_engineering_repair_update).

Previously, this file called save_engineering_update(...) directly at
module level, against the real Supabase database. That meant pytest
attempted a live INSERT the instant it *imported* this file to collect
its tests - during plain `pytest --collect-only` included - and it
only failed to write data because of an unrelated foreign-key
violation, not because anything here stopped it. No test file may
contact the live database merely by being imported or collected; see
tests/conftest.py for the session-wide guard that now enforces this.

Real, live coverage of this same code path already exists deliberately
in tests/test_phase1_mvp_system.py (capture_engineering_update, run
manually against Supabase) - converting this file to offline
mocks/fakes loses no coverage, it only removes the accidental
collection-time side effect.
"""

import importlib
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src import database


UPDATE_FIXTURE = {
    "downtime_event_id": 1,
    "production_run_id": 3,
    "fault_id": 1,
    "engineer": "Aaron",
    "update_type": "Investigation",
    "finding": "Casepacker sensor appears misaligned",
    "action": "Sensor checked and adjusted",
    "engineering_status": "Ongoing",
}


class _FakeCursor:
    def __init__(self, fetchone_result):
        self._fetchone_result = fetchone_result
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        return self._fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, fetchone_result):
        self.cursor_double = _FakeCursor(fetchone_result)
        self.committed = False

    def cursor(self, row_factory=None):
        return self.cursor_double

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_save_engineering_update_inserts_and_returns_the_new_id(monkeypatch):
    fake_connection = _FakeConnection(fetchone_result=(42,))
    monkeypatch.setattr(database, "get_database_connection", lambda: fake_connection)

    result = database.save_engineering_update(UPDATE_FIXTURE)

    assert result == 42
    assert fake_connection.committed is True
    assert fake_connection.cursor_double.last_params == UPDATE_FIXTURE
    assert "INSERT INTO public.engineering_updates" in fake_connection.cursor_double.last_query
    assert "RETURNING id" in fake_connection.cursor_double.last_query


def test_save_engineering_update_raises_when_no_row_is_returned(monkeypatch):
    # Defensive branch: RETURNING id should always yield exactly one row
    # on a successful INSERT, but save_engineering_update still raises a
    # clear, specific error rather than crashing on `None[0]` if it ever
    # doesn't.
    fake_connection = _FakeConnection(fetchone_result=None)
    monkeypatch.setattr(database, "get_database_connection", lambda: fake_connection)

    with pytest.raises(RuntimeError, match="no database ID was returned"):
        database.save_engineering_update(UPDATE_FIXTURE)


def test_importing_this_module_does_not_touch_the_database(monkeypatch):
    """Regression test for the collection-time live INSERT this file
    used to trigger: patch get_database_connection to explode if
    called at all, then re-execute this module's own top-level code
    (exactly what pytest just did to collect it) and prove nothing in
    it calls that function."""

    def _explode(*args, **kwargs):
        raise AssertionError(
            "Importing tests.test_engineering_update must never open a "
            "database connection - any real database call belongs "
            "inside a test function, not at module level."
        )

    monkeypatch.setattr(database, "get_database_connection", _explode)

    this_module = sys.modules[__name__]
    importlib.reload(this_module)
