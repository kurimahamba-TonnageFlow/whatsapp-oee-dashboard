"""
Session-wide safety net: no test module may open a real Supabase/
Postgres connection merely by being imported/collected by pytest -
only by actually running a test that explicitly does so.

Historical incident: an earlier version of tests/test_engineering_update.py
called src.database.save_engineering_update(...) at module level, so
pytest attempted a real Supabase INSERT the instant it imported that
file to collect its tests - during test collection, `pytest
--collect-only` included. It only failed to write data because of an
unrelated foreign-key violation, not because anything stopped it.

This hook patches database.get_database_connection() to raise for the
duration of pytest's collection phase only (module imports, test
discovery) and restores the real function before any test actually
runs:
  - `pytest --collect-only` can never reach a live database, no matter
    what any test module does at import time.
  - A test file that (re-)introduces an import-time database call now
    fails collection loudly and safely, instead of silently attempting
    a live write.
  - Tests that legitimately open a connection from *inside* a test
    function body are unaffected - the guard is removed again before
    any test body executes.
"""

import pytest

from src import database


class DatabaseUsedDuringCollectionError(RuntimeError):
    """Raised if a test module opens a database connection merely by
    being imported/collected, instead of from inside a test function."""


def _blocked_connection(*args, **kwargs):
    raise DatabaseUsedDuringCollectionError(
        "A database connection was attempted while pytest was collecting "
        "tests (importing test modules), not running them. No test file "
        "may contact the live database at import time - move the call "
        "inside a test function, or mock get_database_connection."
    )


@pytest.hookimpl(wrapper=True)
def pytest_collection(session):
    real_connection = database.get_database_connection
    database.get_database_connection = _blocked_connection
    try:
        return (yield)
    finally:
        database.get_database_connection = real_connection
