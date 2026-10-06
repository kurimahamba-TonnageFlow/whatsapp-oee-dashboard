"""
Offline tests for the Stage 6B1/6B2 transaction logic in src/database.py.

src.database.get_database_connection is replaced by a scripted fake:
each cursor.execute() consumes the next scripted result, which the
following fetchone()/fetchall() returns. No real psycopg connection is
ever opened.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
import pytest

from src import database
from src.database import IdempotencyRequest, IdempotentReplay, PulseCaptureError


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class ScriptedCursor:
    def __init__(self, results):
        self._results = list(results)
        self._current = None
        self.calls = []
        self.rowcount = 0

    def execute(self, query, params=None):
        self.calls.append((query, params))
        result = self._results.pop(0) if self._results else None
        if isinstance(result, Exception):
            raise result
        # A DELETE reports how many rows it removed rather than returning
        # them, so a scripted plain int stands for that row count.
        if isinstance(result, int):
            self.rowcount = result
            self._current = None
            return
        self._current = result

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class ScriptedConnection:
    def __init__(self, results):
        self.cursor_obj = ScriptedCursor(results)
        self.committed = False
        self.rolled_back = False

    def cursor(self, row_factory=None):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def script(monkeypatch):
    # Transaction choreography tests isolate the separately integration-tested review query.
    monkeypatch.setattr(database, "_review_period", lambda *a, **k: {"prompt_required": False})
    monkeypatch.setattr(database, "_operating_changes", lambda *a: [])
    def install(*results):
        connection = ScriptedConnection(results)
        monkeypatch.setattr(database, "get_database_connection", lambda: connection)
        return connection

    return install


def run_row(**overrides):
    row = {
        "id": 5, "production_line": "Rovema", "line_technician": "Liam", "shift": "Days",
        "customer": "Asda", "product": "Basmati", "format": "Pillow", "pack_type": "1 kg x 10",
        "pack_weight_kg": Decimal("1.000"), "packs_per_case": 10, "cases_per_pallet": 10,
        "target_speed_ppm": Decimal("8.4"), "starting_pallets_remaining": 25,
        "pallets_remaining": Decimal("25"), "total_pallets_completed": Decimal("0"),
        "potential_overrun_pallets": Decimal("0"), "status": "Active",
        "started_at": utc(2026, 1, 12, 6), "finished_at": None,
    }
    row.update(overrides)
    return row


def test_restore_production_preserves_engineering_and_audits_actual_time(script):
    start, restart, report = utc(2026, 1, 12, 6), utc(2026, 1, 12, 6, 10), utc(2026, 1, 12, 7)
    result = {"downtime_event_id": 8, "production_status": "Resolved", "engineering_status": "Ongoing", "resolved_at": restart}
    connection = script({"id": 8, "production_line": "Rovema", "opened_at": start, "resolved_at": None,
                         "production_status": "Ongoing", "engineering_status": "Ongoing"}, result, None)
    assert database.restore_fault_production(8, "Rovema", "Liam", "Cleared jam", restart, report) == result
    calls = connection.cursor_obj.calls
    assert "FOR UPDATE OF de" in calls[0][0]
    assert "engineering_status =" not in calls[1][0]
    assert calls[1][1]["at"] == restart
    assert calls[2][1]["by"] == "Liam"
    assert calls[2][1]["new"].obj["recorded_at"] == report.isoformat()
    assert connection.committed


@pytest.mark.parametrize('restart', [utc(2026, 1, 12, 5, 59), utc(2026, 1, 12, 7, 1)])
def test_restore_rejects_time_outside_fault_window(script, restart):
    connection = script({"id": 8, "production_line": "Rovema", "opened_at": utc(2026, 1, 12, 6),
                         "resolved_at": None, "production_status": "Ongoing"})
    with pytest.raises(PulseCaptureError):
        database.restore_fault_production(8, "Rovema", "Liam", "Fixed", restart, utc(2026, 1, 12, 7))
    assert not connection.committed
    assert len(connection.cursor_obj.calls) == 1


def test_restore_never_overwrites_existing_restart(script):
    connection = script({"production_line": "Rovema", "resolved_at": utc(2026, 1, 12, 6, 10), "production_status": "Resolved"})
    with pytest.raises(PulseCaptureError):
        database.restore_fault_production(8, "Rovema", "Liam", "Fixed", utc(2026, 1, 12, 6, 15), utc(2026, 1, 12, 7))
    assert len(connection.cursor_obj.calls) == 1


def query_containing(connection, fragment):
    return [(q, p) for q, p in connection.cursor_obj.calls if fragment in q]


def idempotency(respond=lambda result: (201, {"ok": True}), key="key-0000000000000001", action="test:1"):
    return IdempotencyRequest(key=key, action=action, fingerprint="fingerprint-abc", respond=respond)


# ==========================================================
# IDEMPOTENCY
# ==========================================================


def test_claimed_key_is_stored_with_the_response_in_the_same_transaction(script):
    connection = script(
        {"idempotency_key": "key-0000000000000001"},  # claim wins
        run_row(),
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 77},
        {"id": 5},
        None,  # store response
    )

    database.record_hourly_update(
        5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8),
        idempotency=idempotency(respond=lambda result: (201, {"hourly_update_id": result["hourly_update_id"]})),
    )

    claim, claim_params = query_containing(connection, "INSERT INTO public.hmi_idempotency_keys")[0]
    assert "ON CONFLICT (idempotency_key) DO UPDATE" in claim
    assert claim_params["key"] == "key-0000000000000001"
    assert claim_params["production_run_id"] == 5

    store, store_params = query_containing(connection, "UPDATE public.hmi_idempotency_keys")[0]
    assert "response_status" in store and "response_body" in store
    assert store_params["status"] == 201
    assert store_params["body"].obj == {"hourly_update_id": 77}
    assert connection.committed

    # The claim is the very first statement, before the run is even read.
    assert connection.cursor_obj.calls[0][0] is claim


def test_repeat_of_a_completed_request_replays_the_stored_response(script):
    connection = script(
        None,  # claim conflicts
        {"action": "test:1", "request_fingerprint": "fingerprint-abc",
         "response_status": 201, "response_body": {"hourly_update_id": 77}},
    )

    with pytest.raises(IdempotentReplay) as replay:
        database.record_hourly_update(
            5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
        )

    assert replay.value.status_code == 201
    assert replay.value.body == {"hourly_update_id": 77}
    assert connection.rolled_back and not connection.committed
    assert not query_containing(connection, "INSERT INTO public.hourly_updates")


def test_same_key_with_a_different_request_is_a_409(script):
    connection = script(
        None,
        {"action": "test:1", "request_fingerprint": "a-different-fingerprint",
         "response_status": 201, "response_body": {}},
    )

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(
            5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
        )

    assert error.value.status_code == 409
    assert "different details" in error.value.message
    assert connection.rolled_back


def test_key_claimed_but_not_yet_finished_is_a_safe_409(script):
    connection = script(
        None,
        {"action": "test:1", "request_fingerprint": "fingerprint-abc",
         "response_status": None, "response_body": None},
    )

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(
            5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
        )

    assert error.value.status_code == 409
    assert "still being processed" in error.value.message
    assert connection.rolled_back


# ==========================================================
# IDEMPOTENCY RETENTION (90 days)
# ==========================================================


def test_claim_lets_the_database_set_both_timestamps(script):
    """The HMI never sends created_at or expires_at, so it cannot shorten
    its own duplicate protection."""
    connection = script(
        {"idempotency_key": "key-0000000000000001"},
        run_row(),
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
    )

    claim, params = query_containing(connection, "INSERT INTO public.hmi_idempotency_keys")[0]
    assert "created_at = now()" in claim
    assert f"now() + interval '{database.IDEMPOTENCY_RETENTION_DAYS} days'" in claim
    assert "created_at" not in params and "expires_at" not in params


def test_an_expired_key_is_only_taken_over_when_it_has_actually_expired(script):
    """The takeover is guarded by expires_at <= now() in the statement
    itself, so a still-live key can never be overwritten by a race."""
    connection = script(
        {"idempotency_key": "key-0000000000000001"},
        run_row(),
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
    )

    claim, _ = query_containing(connection, "INSERT INTO public.hmi_idempotency_keys")[0]
    assert "ON CONFLICT (idempotency_key) DO UPDATE" in claim
    assert "WHERE public.hmi_idempotency_keys.expires_at <= now()" in claim
    # Taking a key over starts a fresh action - no stale response can be
    # replayed for it afterwards.
    assert "response_status = NULL" in claim
    assert "response_body = NULL" in claim


def test_a_reused_expired_key_becomes_a_new_action_and_writes_again(script):
    """First scripted result is the reclaimed row, i.e. the takeover
    matched. The write then proceeds normally instead of replaying."""
    connection = script(
        {"idempotency_key": "key-0000000000000001"},  # expired row reclaimed
        run_row(),
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 78},
        {"id": 5},
        None,
    )

    saved = database.record_hourly_update(
        5, utc(2026, 1, 12, 7), Decimal("1.25"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
    )

    assert saved["hourly_update_id"] == 78
    assert query_containing(connection, "INSERT INTO public.hourly_updates")
    assert connection.committed


def test_a_live_key_still_replays_rather_than_being_taken_over(script):
    """The takeover WHERE did not match, so the claim returns nothing and
    the stored response is replayed exactly as before."""
    connection = script(
        None,
        {"action": "test:1", "request_fingerprint": "fingerprint-abc",
         "response_status": 201, "response_body": {"hourly_update_id": 77}},
    )

    with pytest.raises(IdempotentReplay) as replay:
        database.record_hourly_update(
            5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
        )

    assert replay.value.body == {"hourly_update_id": 77}
    assert not query_containing(connection, "INSERT INTO public.hourly_updates")


def test_cleanup_deletes_only_expired_rows(script):
    connection = script(4)

    assert database.delete_expired_idempotency_keys() == 4

    statement, params = connection.cursor_obj.calls[0]
    assert "DELETE FROM public.hmi_idempotency_keys" in statement
    assert "WHERE expires_at <= now()" in statement
    # No key, action or "delete everything" escape hatch exists.
    assert params == {}
    assert "idempotency_key =" not in statement


def test_cleanup_can_run_in_batches_without_widening_the_filter(script):
    connection = script(500)

    assert database.delete_expired_idempotency_keys(batch_size=500) == 500

    statement, params = connection.cursor_obj.calls[0]
    assert statement.count("expires_at <= now()") == 1
    assert params == {"batch_size": 500}


def test_cleanup_rejects_a_meaningless_batch_size():
    with pytest.raises(ValueError):
        database.delete_expired_idempotency_keys(batch_size=0)


def test_no_hmi_write_path_deletes_idempotency_keys(script):
    """Retention is a scheduled maintenance operation. An operator's
    hourly update must never trigger an unbounded DELETE."""
    connection = script(
        {"idempotency_key": "key-0000000000000001"},
        run_row(),
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
    )

    assert not query_containing(connection, "DELETE FROM public.hmi_idempotency_keys")


# ==========================================================
# CROSS-DEVICE LINE STATE
# ==========================================================


def test_line_state_reads_every_active_configured_line(script):
    connection = script([
        {"line_id": 1, "line_name": "Rovema", "run_id": 5},
        {"line_id": 2, "line_name": "GIC", "run_id": None},
    ])

    rows = database.get_hmi_line_state()

    assert [row["line_name"] for row in rows] == ["Rovema", "GIC"]

    query, params = connection.cursor_obj.calls[0]
    assert params is None
    assert "FROM public.production_lines" in query
    assert "WHERE pl.active = true" in query
    assert "r.status = 'Active'" in query


@pytest.mark.parametrize(
    "management_only",
    ["tonne", "tonnage", "oee", "achievement", "weekly_tonnage_targets", "waste", "cost", "xray"],
)
def test_line_state_query_exposes_no_management_only_information(script, management_only):
    """The factory-floor HMI is unauthenticated, so this query must not
    reach for tonnage, achievement, OEE, targets, waste or cost."""
    connection = script([])

    database.get_hmi_line_state()

    query, _ = connection.cursor_obj.calls[0]
    assert management_only not in query.lower()


def test_line_state_returns_open_planned_downtime_changeover_and_faults(script):
    connection = script([{
        "line_id": 1, "line_name": "Rovema", "run_id": 5,
        "open_planned_downtime_id": 9, "open_changeover_id": 3, "open_fault_count": 2,
    }])

    rows = database.get_hmi_line_state()

    assert rows[0]["open_planned_downtime_id"] == 9
    assert rows[0]["open_changeover_id"] == 3
    assert rows[0]["open_fault_count"] == 2

    query, _ = connection.cursor_obj.calls[0]
    assert "pde.ended_at IS NULL" in query
    assert "co.status = 'Open'" in query
    assert "de.production_status = 'Ongoing'" in query


# ==========================================================
# HOURLY UPDATE
# ==========================================================


ONE_HOUR = utc(2026, 1, 1, 1) - utc(2026, 1, 1)


def test_record_hourly_update_persists_decimal_pallets_and_progress(script):
    connection = script(
        run_row(),
        None,  # hour 07:00-08:00 not yet reported
        [],    # no speed changes
        [{"reason": "Film Change", "started_at": utc(2026, 1, 12, 7, 30), "ended_at": utc(2026, 1, 12, 7, 40)}],
        {"id": 77},
        {"id": 5},
    )

    saved = database.record_hourly_update(5, utc(2026, 1, 12, 7), Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8, 10))

    assert connection.committed and not connection.rolled_back
    assert "FOR UPDATE" in connection.cursor_obj.calls[0][0]

    insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["hour_start"] == utc(2026, 1, 12, 7)
    assert params["pallets_completed"] == Decimal("3.7500")
    # The whole clock hour at 8.4 ppm; the stop lowers actual output, not the target.
    assert params["expected_packs"] == Decimal("504.0000")
    assert params["planned_downtime_minutes"] == Decimal("10.0000")
    assert params["planned_downtime"] == "Film Change"
    assert params["period_started_at"] == utc(2026, 1, 12, 7)
    assert params["period_ended_at"] == utc(2026, 1, 12, 8)
    assert params["recorded_at"] == utc(2026, 1, 12, 8, 10)  # submission time kept as created_at
    assert "'react_hmi'" in insert and "hour_start" in insert

    _update, progress = query_containing(connection, "UPDATE public.production_runs")[0]
    assert progress["pallets_remaining"] == Decimal("21.2500")
    assert saved["hourly_update_id"] == 77
    assert saved["hour_label"] == "07:00–08:00"


def test_partial_first_hour_covers_only_the_minutes_after_the_run_started(script):
    connection = script(run_row(started_at=utc(2026, 1, 12, 6, 25)), None, [], [], {"id": 1}, {"id": 5})

    database.record_hourly_update(5, utc(2026, 1, 12, 6), Decimal(2), "Liam", None, utc(2026, 1, 12, 7, 10))

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["period_started_at"] == utc(2026, 1, 12, 6, 25)
    assert params["period_ended_at"] == utc(2026, 1, 12, 7)
    assert params["period_minutes"] == Decimal("35.0000")
    assert params["expected_packs"] == Decimal("294.0000")  # 35 x 8.4


def test_mid_hour_speed_change_uses_the_speed_in_force_in_each_part(script):
    connection = script(
        run_row(target_speed_ppm=Decimal(12)),
        None,
        [{"previous_speed_ppm": Decimal(6), "new_speed_ppm": Decimal(12), "effective_at": utc(2026, 1, 12, 7, 20)}],
        [],
        {"id": 2},
        {"id": 5},
    )

    database.record_hourly_update(5, utc(2026, 1, 12, 7), Decimal(5), "Liam", None, utc(2026, 1, 12, 8, 5))

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["expected_packs"] == Decimal("600.0000")  # 20 x 6 + 40 x 12


def test_each_missed_hour_is_reported_on_its_own(script):
    """Three hours missed: each is its own reading - never one pallet
    count spread over several hours."""
    for hour in (7, 8, 9):
        connection = script(run_row(), None, [], [], {"id": hour}, {"id": 5})
        database.record_hourly_update(5, utc(2026, 1, 12, hour), Decimal(4), "Liam", None, utc(2026, 1, 12, 10, 15))
        _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
        assert params["hour_start"] == utc(2026, 1, 12, hour)
        assert params["period_minutes"] == Decimal("60.0000")


def test_an_hour_already_reported_is_refused_and_nothing_is_written(script):
    connection = script(run_row(), {"id": 70})

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, utc(2026, 1, 12, 7), Decimal(1), "Liam", None, utc(2026, 1, 12, 8, 10))

    assert error.value.status_code == 409
    assert "07:00–08:00 has already been reported" in error.value.message
    assert connection.rolled_back
    assert not query_containing(connection, "INSERT INTO public.hourly_updates")


def test_an_hour_that_has_not_finished_cannot_be_reported(script):
    connection = script(run_row())

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, utc(2026, 1, 12, 8), Decimal(1), "Liam", None, utc(2026, 1, 12, 8, 40))

    assert error.value.status_code == 409
    assert "has not finished yet" in error.value.message
    assert connection.rolled_back


def test_an_hour_outside_the_run_is_refused(script):
    connection = script(run_row(started_at=utc(2026, 1, 12, 9)))

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, utc(2026, 1, 12, 7), Decimal(1), "Liam", None, utc(2026, 1, 12, 10))

    assert error.value.status_code == 422
    assert connection.rolled_back


def test_a_part_hour_is_not_a_clock_hour(script):
    connection = script(run_row())

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, utc(2026, 1, 12, 7, 30), Decimal(1), "Liam", None, utc(2026, 1, 12, 9))

    assert error.value.status_code == 422
    assert connection.rolled_back


@pytest.mark.parametrize("run, status", [(None, 404), (run_row(status="Completed"), 409)])
def test_hourly_update_requires_an_existing_active_run(script, run, status):
    connection = script(run)

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, utc(2026, 1, 12, 7), Decimal(1), "Liam", None, utc(2026, 1, 12, 8))

    assert error.value.status_code == status
    assert connection.rolled_back


# ==========================================================
# SHIFT ATTRIBUTION: by the clock hour, every boundary and DST
# ==========================================================


@pytest.mark.parametrize(
    "hour_start, expected_shift, expected_window_start",
    [
        (utc(2026, 1, 12, 13), "Day", utc(2026, 1, 12, 6)),        # 13:00-14:00 GMT
        (utc(2026, 1, 12, 14), "Afternoon", utc(2026, 1, 12, 14)),  # 14:00-15:00 GMT
        (utc(2026, 1, 12, 21), "Afternoon", utc(2026, 1, 12, 14)),
        (utc(2026, 1, 12, 22), "Night", utc(2026, 1, 12, 22)),
        (utc(2026, 1, 13, 5), "Night", utc(2026, 1, 12, 22)),       # after midnight
        (utc(2026, 7, 13, 12), "Day", utc(2026, 7, 13, 5)),         # 13:00-14:00 BST
        (utc(2026, 7, 13, 13), "Afternoon", utc(2026, 7, 13, 13)),  # 14:00-15:00 BST
    ],
)
def test_each_hour_belongs_to_the_shift_it_falls_in(script, hour_start, expected_shift, expected_window_start):
    connection = script(
        run_row(shift="Days", started_at=utc(2026, 1, 1)), None, [], [], {"id": 9}, {"id": 5}
    )

    database.record_hourly_update(5, hour_start, Decimal(1), "Liam", None, hour_start + ONE_HOUR)

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["shift"] == expected_shift
    assert params["shift_window_start"] == expected_window_start


# ==========================================================
# END RUN: final part hour, open stops, mid-run captures
# ==========================================================


def test_end_run_final_reading_covers_the_current_hour_up_to_end_run(script):
    connection = script(
        run_row(),
        None,          # no open planned stop
        None, [], [],  # final hour not yet reported; no speed changes; no stops
        {"id": 90},
        {"id": 5},
        {"covered_to": None},
        {"pallets": Decimal("10"), "last_id": 90},
        {"pallets": Decimal("10"), "last_id": 90},
        {"id": 4, "captured_at": utc(2026, 1, 12, 13, 40)},
        {"id": 5},
    )

    database.record_xray_capture(5, xray_capture(1000, final=Decimal("1.25")), utc(2026, 1, 12, 13, 40), True)

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["hour_start"] == utc(2026, 1, 12, 13)
    assert params["period_started_at"] == utc(2026, 1, 12, 13)
    assert params["period_ended_at"] == utc(2026, 1, 12, 13, 40)  # output clock stops at End Run
    assert params["expected_packs"] == Decimal("336.0000")         # 40 min x 8.4


def test_end_run_is_refused_while_a_planned_stop_is_open(script):
    connection = script(run_row(), {"reason": "Cleaning"})

    with pytest.raises(PulseCaptureError) as error:
        database.record_xray_capture(5, xray_capture(1000), utc(2026, 1, 12, 13, 40), True)

    assert error.value.status_code == 409
    assert "End the Cleaning planned stop" in error.value.message
    assert connection.rolled_back
    assert not query_containing(connection, "SET status = 'Completed'")


def test_a_mid_run_capture_cannot_carry_pallets_and_split_an_hour(script):
    connection = script(run_row(), None)

    with pytest.raises(PulseCaptureError) as error:
        database.record_xray_capture(5, xray_capture(1000, final=Decimal(1)), utc(2026, 1, 12, 13, 40), False)

    assert error.value.status_code == 409
    assert connection.rolled_back
    assert not query_containing(connection, "INSERT INTO public.hourly_updates")


# ==========================================================
# HANDOVER: line stoppages, carried faults, next run
# ==========================================================

ENDED_RUN = {
    "id": 5, "finished_at": utc(2026, 1, 12, 13, 40), "target_speed_ppm": Decimal("8.4"),
    "line_technician": "Liam", "customer": "Asda", "product": "Basmati",
    "pack_weight_kg": Decimal("1.000"), "format": "Pillow",
}


def stoppage_row(**overrides):
    row = {
        "id": 11, "production_line": "Rovema", "kind": "changeover", "reason": None,
        "previous_production_run_id": 5, "next_production_run_id": None, "started_by": "Liam",
        "started_at": utc(2026, 1, 12, 13, 42), "ended_by": None, "ended_at": None, "duration_minutes": None,
        "physical_ended_at": None, "physical_ended_by": None, "follows_stoppage_id": None,
    }
    row.update(overrides)
    return row


def test_changeover_starts_a_line_stop_and_its_qa_record_from_the_ended_run(script):
    connection = script(
        None,           # no active run on the line
        None,           # no open line stop
        ENDED_RUN,      # the run that just ended
        None,           # nothing chosen for it yet
        stoppage_row(),
        {"id": 21, "status": "Open"},
    )

    result = database.start_line_stoppage("Rovema", "changeover", None, "Liam", utc(2026, 1, 12, 13, 42))

    _q, stop_params = query_containing(connection, "INSERT INTO public.line_stoppages")[0]
    assert stop_params["previous_run_id"] == 5 and stop_params["kind"] == "changeover"
    # Starts when the run ENDED (13:40), not when the choice was tapped (13:42).
    assert stop_params["started_at"] == ENDED_RUN["finished_at"]
    changeover_sql, co_params = query_containing(connection, "INSERT INTO public.changeovers")[0]
    inserted_columns = changeover_sql.split("VALUES")[0]
    assert "line_stoppage_id" in inserted_columns and "planned_downtime_event_id" not in inserted_columns
    assert co_params["product"] == "Basmati" and co_params["stoppage_id"] == 11
    # No product run is charged: nothing is written to planned_downtime_events.
    assert not query_containing(connection, "INSERT INTO public.planned_downtime_events")
    assert result["changeover"]["id"] == 21
    assert connection.committed


def test_other_stop_has_no_qa_record(script):
    connection = script(None, None, ENDED_RUN, None, stoppage_row(kind="other", reason="Power cut"))

    database.start_line_stoppage("Rovema", "other", "Power cut", "Liam", utc(2026, 1, 12, 13, 42))

    assert not query_containing(connection, "INSERT INTO public.changeovers")
    assert connection.committed


def test_a_line_stop_needs_the_run_ended_first(script):
    connection = script({"id": 5})

    with pytest.raises(PulseCaptureError) as error:
        database.start_line_stoppage("Rovema", "changeover", None, "Liam", utc(2026, 1, 12, 13, 42))

    assert error.value.status_code == 409
    assert connection.rolled_back


def test_end_changeover_marks_the_physical_work_done_and_keeps_the_event_running(script):
    connection = script(
        stoppage_row(physical_ended_at=None, physical_ended_by=None),
        stoppage_row(physical_ended_at=utc(2026, 1, 12, 14, 12), physical_ended_by="Liam"),
    )

    result = database.end_line_stoppage(11, "Liam", utc(2026, 1, 12, 14, 12))

    update, params = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert "physical_ended_at = %(at)s" in update and "ended_at = %(" not in update.replace("physical_ended_at", "")
    assert params["at"] == utc(2026, 1, 12, 14, 12)
    # The QA record is NOT completed here: the event runs through the new-run form.
    assert not query_containing(connection, "UPDATE public.changeovers")
    assert result["stoppage"]["physical_ended_at"] == utc(2026, 1, 12, 14, 12)
    assert connection.committed


def test_a_repeated_end_changeover_tap_changes_nothing(script):
    already = stoppage_row(physical_ended_at=utc(2026, 1, 12, 14, 12), physical_ended_by="Liam")
    connection = script(already)

    result = database.end_line_stoppage(11, "Liam", utc(2026, 1, 12, 14, 20))

    assert not query_containing(connection, "UPDATE public.line_stoppages")
    assert result["stoppage"]["physical_ended_at"] == utc(2026, 1, 12, 14, 12)


def test_a_handover_is_only_ended_by_the_incoming_run(script):
    connection = script(stoppage_row(kind="handover", physical_ended_at=None, physical_ended_by=None))

    with pytest.raises(PulseCaptureError) as error:
        database.end_line_stoppage(11, "Ben", utc(2026, 1, 12, 14, 20))

    assert error.value.status_code == 409
    assert connection.rolled_back


def test_a_stop_cannot_end_twice(script):
    connection = script(stoppage_row(ended_at=utc(2026, 1, 12, 14)))

    with pytest.raises(PulseCaptureError) as error:
        database.end_line_stoppage(11, "Liam", utc(2026, 1, 12, 14, 12))

    assert error.value.status_code == 409
    assert connection.rolled_back


NEW_RUN = {
    "production_line": "Rovema", "line_technician": "Ben", "shift": "Afternoons", "customer": "Tesco",
    "product": "Jasmine", "pack_weight_kg": 0.5, "packs_per_case": 10, "pack_type": "Pillow",
    "target_speed_ppm": 60, "cases_per_pallet": 100, "starting_pallets_remaining": 10,
    "pallets_remaining": 10, "previous_run_completed": 0, "format": "Block",
}


def test_a_new_run_cannot_start_before_end_changeover(script):
    connection = script(None, stoppage_row(physical_ended_at=None, physical_ended_by=None))

    with pytest.raises(PulseCaptureError) as error:
        database.create_production_run(NEW_RUN)

    assert error.value.status_code == 409
    assert "End Changeover" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.production_runs")


def test_carried_faults_must_be_acknowledged_before_the_incoming_run(script):
    connection = script(
        None, None, ENDED_RUN, {"state": "recorded"},
        [{"downtime_event_id": 2, "acknowledged": False}, {"downtime_event_id": 3, "acknowledged": True}],
    )

    with pytest.raises(PulseCaptureError) as error:
        database.create_production_run(NEW_RUN)

    assert error.value.status_code == 409
    assert "Acknowledge and escalate the 1 open fault" in error.value.message
    # Acknowledgements only count from the handover (the ended run's finish).
    _q, params = query_containing(connection, "FROM public.fault_acknowledgements")[0]
    assert params["since"] == ENDED_RUN["finished_at"]
    assert not query_containing(connection, "INSERT INTO public.production_runs")


def test_the_new_run_closes_the_changeover_with_its_own_settings(script):
    connection = script(
        None, None, ENDED_RUN, {"state": "recorded"}, [],   # ready: next step chosen, faults acknowledged
        {"id": 31},                   # new run
        [{"id": 11, "kind": "changeover"}],
        None,                         # changeover record updated
    )

    result = database.create_production_run(NEW_RUN)

    assert result["run_id"] == 31
    _q, link = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert link["new_run_id"] == 31 and link["previous_run_id"] == 5
    _q, co = query_containing(connection, "UPDATE public.changeovers")[0]
    assert co["product"] == "Jasmine" and co["pack_weight_kg"] == 0.5 and co["stoppage_ids"] == [11]
    assert connection.committed


def test_a_new_run_cannot_bypass_an_unresolved_next_step(script):
    """End Run confirmed, but nobody chose End Shift / Changeover / Other
    - however long ago. Start Run is refused so the gap is not absorbed."""
    connection = script(None, None, ENDED_RUN, None)

    with pytest.raises(PulseCaptureError) as error:
        database.create_production_run({**NEW_RUN, "line_technician": "Ben"})

    assert error.value.status_code == 409
    assert "Choose what happened after the last run on Rovema" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.production_runs")
    assert connection.rolled_back


def test_acknowledging_a_fault_updates_it_and_never_creates_another(script):
    connection = script(
        {"id": 2, "production_status": "Ongoing", "production_line": "GIC"},
        {"id": 8, "acknowledged_at": utc(2026, 1, 12, 14, 1)},
        {"downtime_event_id": 2, "escalation_count": 3, "last_escalated_at": utc(2026, 1, 12, 14, 1),
         "last_escalated_by": "Ben"},
    )

    result = database.acknowledge_line_fault(2, "GIC", "Ben", "Still jamming", utc(2026, 1, 12, 14, 1))

    assert not query_containing(connection, "INSERT INTO public.downtime_events")
    update, _p = query_containing(connection, "UPDATE public.downtime_events")[0]
    assert "COALESCE(escalation_count, 0) + 1" in update
    assert result["escalation_count"] == 3
    assert connection.committed


def test_a_closed_fault_cannot_be_acknowledged(script):
    connection = script({"id": 2, "production_status": "Resolved", "production_line": "GIC"})

    with pytest.raises(PulseCaptureError) as error:
        database.acknowledge_line_fault(2, "GIC", "Ben", None, utc(2026, 1, 12, 14, 1))

    assert error.value.status_code == 409
    assert connection.rolled_back


@pytest.mark.parametrize("speed", [Decimal(10), Decimal("8.4")])
def test_retired_target_change_never_mutates_history(script, speed):
    connection = script()
    with pytest.raises(PulseCaptureError) as error:
        database.record_target_speed_change(5, speed, "New film", "Liam", utc(2026,1,12,9))
    assert error.value.status_code == 409
    assert not connection.cursor_obj.calls


# ==========================================================
# PLANNED DOWNTIME
# ==========================================================


def test_start_planned_downtime_rejects_a_second_open_stop(script):
    connection = script(run_row(), {"id": 3})

    with pytest.raises(PulseCaptureError) as error:
        database.start_planned_downtime(5, "Film Change", "Liam", utc(2026, 1, 12, 8))

    assert error.value.status_code == 409
    assert connection.rolled_back
    assert not query_containing(connection, "INSERT")


def test_end_planned_downtime_stores_exact_duration(script):
    connection = script(
        {"id": 3, "started_at": utc(2026, 1, 12, 7, 30), "ended_at": None},
        None,  # not part of a changeover
        {"id": 3, "duration_minutes": Decimal("12.5")},
    )

    database.end_planned_downtime(3, "Liam", utc(2026, 1, 12, 7, 42, 30))

    update, params = query_containing(connection, "UPDATE public.planned_downtime_events")[0]
    assert params["duration_minutes"] == Decimal("12.5000")
    assert "ended_at IS NULL" in update
    assert connection.committed


def test_a_changeovers_planned_stop_cannot_be_ended_directly(script):
    connection = script(
        {"id": 3, "started_at": utc(2026, 1, 12, 7, 30), "ended_at": None},
        {"id": 6},  # an open changeover owns this stop
    )

    with pytest.raises(PulseCaptureError) as error:
        database.end_planned_downtime(3, "Liam", utc(2026, 1, 12, 8))

    assert error.value.status_code == 409
    assert "Changeover Complete" in error.value.message
    assert connection.rolled_back
    assert not query_containing(connection, "UPDATE public.planned_downtime_events")


@pytest.mark.parametrize(
    "row, status",
    [
        (None, 404),
        ({"id": 3, "started_at": utc(2026, 1, 12, 7), "ended_at": utc(2026, 1, 12, 7, 10)}, 409),
        ({"id": 3, "started_at": utc(2026, 1, 12, 9), "ended_at": None}, 409),
    ],
)
def test_end_planned_downtime_rejections(script, row, status):
    connection = script(row)

    with pytest.raises(PulseCaptureError) as error:
        database.end_planned_downtime(3, "Liam", utc(2026, 1, 12, 8))

    assert error.value.status_code == status
    assert connection.rolled_back


# ==========================================================
# REPORT TO ENGINEER
# ==========================================================


def test_report_fault_uses_next_fault_id_and_configured_machine_and_button(script):
    connection = script(
        run_row(),
        {"id": 7, "name": "BV1 Bagger", "active": True, "production_line": "Rovema"},
        {"id": 12, "machine_id": 7, "name": "Film Jam", "event_type": "unplanned_fault", "active": True},
        {"next_fault_id": 4},
        {"id": 41, "production_run_id": 5, "fault_id": 4, "machine": "BV1 Bagger", "reason": "Film Jam",
         "reported_by": "Liam", "production_status": "Ongoing", "engineering_status": "Not Started",
         "opened_at": utc(2026, 1, 12, 8)},
    )

    database.report_fault_to_engineering(
        5,
        {"machine": "BV1", "machine_id": 7, "button_id": 12, "reason": "typed over by the button",
         "reported_by": "Liam", "note": None},
        utc(2026, 1, 12, 8),
    )

    insert, params = query_containing(connection, "INSERT INTO public.downtime_events")[0]
    assert params["fault_id"] == 4
    assert params["machine"] == "BV1 Bagger"
    assert params["reason"] == "Film Jam"
    assert "'Not Started'" in insert
    assert params["production_status"] == "Ongoing"
    assert params["engineer_called"] is True
    assert "'react_hmi'" in insert
    assert connection.committed


def test_report_fault_rejects_machine_from_another_line(script):
    connection = script(run_row(), {"id": 7, "name": "GIC Filler", "active": True, "production_line": "GIC"})

    with pytest.raises(PulseCaptureError) as error:
        database.report_fault_to_engineering(
            5, {"machine": "x", "machine_id": 7, "reason": "Jam", "reported_by": "Liam"}, utc(2026, 1, 12, 8)
        )

    assert error.value.status_code == 422
    assert connection.rolled_back


def test_report_fault_rejects_button_of_another_machine(script):
    connection = script(
        run_row(),
        {"id": 7, "name": "BV1", "active": True, "production_line": "Rovema"},
        {"id": 12, "machine_id": 8, "name": "Jam", "event_type": "unplanned_fault", "active": True},
    )

    with pytest.raises(PulseCaptureError) as error:
        database.report_fault_to_engineering(
            5, {"machine": "BV1", "machine_id": 7, "button_id": 12, "reason": "Jam", "reported_by": "Liam"},
            utc(2026, 1, 12, 8),
        )

    assert error.value.status_code == 422
    assert connection.rolled_back


# ==========================================================
# X-RAY CAPTURE AND RUN COMPLETION
# ==========================================================


def xray_capture(count=1000, available=True, reason=None, final=None):
    return {
        "line_technician": "Liam",
        "final_pallets_produced": final,
        "count_available": available,
        "xray_pack_count": count if available else None,
        "unavailable_reason": reason,
    }


def test_shift_end_xray_snapshots_palletised_packs_since_previous_capture(script):
    connection = script(
        run_row(),
        None,                                          # no shift_end capture yet for this shift
        {"covered_to": 10},                            # previous coverage
        {"pallets": Decimal("8.75"), "last_id": 12},   # uncovered pallets
        {"pallets": Decimal("18.75"), "last_id": 12},  # total pallets
        {"id": 3, "captured_at": utc(2026, 1, 12, 13, 55)},
    )

    saved = database.record_xray_capture(5, xray_capture(1000), utc(2026, 1, 12, 13, 55), False)

    _insert, params = query_containing(connection, "INSERT INTO public.production_run_xray_counts")[0]
    assert params["palletised_pallets"] == Decimal("8.7500")
    assert params["palletised_packs"] == Decimal("875.0000")
    assert params["covered_to"] == 12
    assert params["difference"] == Decimal("125.0000")
    assert params["waste_percent"] == Decimal("12.5000")
    assert params["waste_status"] == "estimated"
    assert params["capture_point"] == "shift_end"
    assert params["shift"] == "Day"
    assert not query_containing(connection, "SET status = 'Completed'")
    assert saved["total_pallets_recorded"] == Decimal("18.75")
    assert connection.committed


def test_xray_below_palletised_is_stored_as_warning_with_no_waste_percentage(script):
    connection = script(
        run_row(), None, {"covered_to": None},
        {"pallets": Decimal("8.75"), "last_id": 11},
        {"pallets": Decimal("8.75"), "last_id": 11},
        {"id": 3, "captured_at": utc(2026, 1, 12, 13, 55)},
    )

    saved = database.record_xray_capture(5, xray_capture(800), utc(2026, 1, 12, 13, 55), False)

    _insert, params = query_containing(connection, "INSERT INTO public.production_run_xray_counts")[0]
    assert params["waste_status"] == "data_quality_warning"
    assert params["difference"] == Decimal("-75.0000")
    assert params["waste_percent"] is None
    assert saved["warning"]


def test_unavailable_xray_count_stores_reason_and_no_waste(script):
    connection = script(
        run_row(), None, {"covered_to": None},
        {"pallets": Decimal(0), "last_id": None},
        {"pallets": Decimal(0), "last_id": None},
        {"id": 3, "captured_at": utc(2026, 1, 12, 13, 55)},
    )

    database.record_xray_capture(
        5, xray_capture(available=False, reason="Counter offline"), utc(2026, 1, 12, 13, 55), False
    )

    _insert, params = query_containing(connection, "INSERT INTO public.production_run_xray_counts")[0]
    assert params["count_available"] is False
    assert params["xray_pack_count"] is None
    assert params["unavailable_reason"] == "Counter offline"
    assert params["difference"] is None
    assert params["waste_percent"] is None
    assert params["waste_status"] == "unavailable"


def test_second_shift_end_capture_in_the_same_shift_is_rejected(script):
    connection = script(run_row(), {"id": 2})

    with pytest.raises(PulseCaptureError) as error:
        database.record_xray_capture(5, xray_capture(), utc(2026, 1, 12, 13, 55), False)

    assert error.value.status_code == 409
    assert connection.rolled_back


def test_run_completion_saves_final_production_before_the_xray_and_closes_the_run(script):
    connection = script(
        run_row(),
        None,  # no open planned stop
        # final hourly update
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 90},
        {"id": 5},
        # xray coverage
        {"covered_to": None},
        {"pallets": Decimal("10"), "last_id": 90},
        {"pallets": Decimal("10"), "last_id": 90},
        {"id": 4, "captured_at": utc(2026, 1, 12, 13, 55)},
        {"id": 5},  # run closed
    )

    saved = database.record_xray_capture(
        5, xray_capture(1000, final=Decimal("1.25")), utc(2026, 1, 12, 13, 55), True
    )

    queries = [q for q, _p in connection.cursor_obj.calls]
    hourly_index = next(i for i, q in enumerate(queries) if "INSERT INTO public.hourly_updates" in q)
    xray_index = next(i for i, q in enumerate(queries) if "INSERT INTO public.production_run_xray_counts" in q)
    close_index = next(i for i, q in enumerate(queries) if "SET status = 'Completed'" in q)
    assert hourly_index < xray_index < close_index

    _insert, hourly_params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert hourly_params["pallets_completed"] == Decimal("1.2500")
    assert saved["final_hourly_update"]["hourly_update_id"] == 90
    # The final pallets are inside the palletised figure the X-ray is compared with.
    _x, xray_params = query_containing(connection, "INSERT INTO public.production_run_xray_counts")[0]
    assert xray_params["palletised_packs"] == Decimal("1000.0000")
    assert connection.committed and not connection.rolled_back


def test_completing_a_run_is_refused_when_palletised_packs_exceed_the_xray_count(script):
    """Completing is final and cannot be undone from the HMI, so it must
    not close on figures that contradict each other. The final hourly
    update inserted moments earlier is rolled back with it."""
    connection = script(
        run_row(),
        None,  # no open planned stop
        None, [],  # hour not yet reported; no speed changes
        [],
        {"id": 90},
        {"id": 5},
        {"covered_to": None},
        {"pallets": Decimal("100"), "last_id": 90},   # 100 pallets -> 10000 packs
        {"pallets": Decimal("100"), "last_id": 90},
    )

    with pytest.raises(PulseCaptureError) as error:
        database.record_xray_capture(
            5, xray_capture(9800, final=Decimal("1.25")), utc(2026, 1, 12, 13, 55), True
        )

    assert error.value.status_code == 409
    assert "lower than" in error.value.message
    assert connection.rolled_back and not connection.committed
    # Nothing was written: no X-ray row and no run closure.
    assert not query_containing(connection, "INSERT INTO public.production_run_xray_counts")
    assert not query_containing(connection, "SET status = 'Completed'")


def test_a_shift_end_capture_with_the_same_shortfall_is_still_recorded(script):
    """An end-of-shift count is a mid-run observation, not a final
    action: it is stored with its warning and no waste percentage, and is
    excluded from waste reporting because its status is not 'estimated'."""
    connection = script(
        run_row(),
        None,                                        # no shift_end capture yet this shift
        {"covered_to": None},
        {"pallets": Decimal("100"), "last_id": 90},  # 100 pallets -> 10000 packs
        {"pallets": Decimal("100"), "last_id": 90},
        {"id": 4, "captured_at": utc(2026, 1, 12, 13, 55)},
    )

    saved = database.record_xray_capture(5, xray_capture(9800), utc(2026, 1, 12, 13, 55), False)

    assert saved["waste_status"] == "data_quality_warning"
    assert saved["post_xray_pack_difference"] == Decimal(-200)
    assert saved["estimated_post_xray_waste_percent"] is None
    assert connection.committed

    _q, params = query_containing(connection, "INSERT INTO public.production_run_xray_counts")[0]
    # Stored signed - never abs(), never clamped to zero.
    assert params["difference"] == Decimal("-200.0000")
    assert params["waste_percent"] is None
    assert params["waste_status"] == "data_quality_warning"


def test_run_completion_rolls_everything_back_if_the_run_was_already_closed(script):
    connection = script(
        run_row(), None, {"covered_to": None},
        {"pallets": Decimal(0), "last_id": None},
        {"pallets": Decimal(0), "last_id": None},
        {"id": 4, "captured_at": utc(2026, 1, 12, 13, 55)},
        None,  # guarded close matched no row
    )

    with pytest.raises(PulseCaptureError) as error:
        database.record_xray_capture(5, xray_capture(0), utc(2026, 1, 12, 13, 55), True)

    assert error.value.status_code == 409
    assert connection.rolled_back and not connection.committed


# ==========================================================
# CHANGEOVERS (paired with their planned stop)
# ==========================================================

NEW_CONFIGURATION = {
    "new_customer": "Tesco",
    "new_product": "Jasmine",
    "new_pack_weight_kg": Decimal("4"),
    "new_format": "Block bottom",
}


def test_start_changeover_creates_the_planned_stop_and_record_together(script):
    connection = script(
        run_row(),
        None,  # no open planned stop
        None,  # no open changeover on the line
        {"id": 3, "production_run_id": 5, "production_line": "Rovema", "reason": "Changeover",
         "started_by": "Liam", "started_at": utc(2026, 1, 12, 15), "ended_by": None,
         "ended_at": None, "duration_minutes": None},
        {"id": 6, "status": "Open"},
    )

    result = database.start_run_changeover(5, "Liam", NEW_CONFIGURATION, None, utc(2026, 1, 12, 15))

    planned_insert, planned_params = query_containing(connection, "INSERT INTO public.planned_downtime_events")[0]
    assert "'Changeover'" in planned_insert
    assert planned_params["started_by"] == "Liam"

    _changeover_insert, params = query_containing(connection, "INSERT INTO public.changeovers")[0]
    assert params["planned_id"] == 3
    assert params["previous_customer"] == "Asda"
    assert params["previous_product"] == "Basmati"
    assert params["previous_pack_weight_kg"] == Decimal("1.000")
    assert params["previous_format"] == "Pillow"
    assert params["new_customer"] == "Tesco"
    assert params["shift"] == "Day"
    assert result["changeover"]["id"] == 6
    assert connection.committed


@pytest.mark.parametrize("open_planned, open_changeover", [({"id": 3}, None), (None, {"id": 6})])
def test_start_changeover_conflicts_leave_nothing_behind(script, open_planned, open_changeover):
    connection = script(run_row(), open_planned, open_changeover)

    with pytest.raises(PulseCaptureError) as error:
        database.start_run_changeover(5, "Liam", NEW_CONFIGURATION, None, utc(2026, 1, 12, 15))

    assert error.value.status_code == 409
    assert connection.rolled_back
    assert not query_containing(connection, "INSERT INTO public.planned_downtime_events")
    assert not query_containing(connection, "INSERT INTO public.changeovers")


def test_start_changeover_race_on_the_unique_index_rolls_back_the_planned_stop(script):
    connection = script(
        run_row(), None, None,
        {"id": 3},
        psycopg.errors.UniqueViolation("duplicate key"),
    )

    with pytest.raises(PulseCaptureError) as error:
        database.start_run_changeover(5, "Liam", NEW_CONFIGURATION, None, utc(2026, 1, 12, 15))

    assert error.value.status_code == 409
    assert connection.rolled_back and not connection.committed


def open_changeover_row(**overrides):
    row = {
        "id": 6, "production_line": "Rovema", "status": "Open", "started_at": utc(2026, 1, 12, 15),
        "planned_downtime_event_id": 3,
    }
    row.update(overrides)
    return row


def test_complete_changeover_ends_its_planned_stop_in_the_same_transaction(script):
    connection = script(
        open_changeover_row(),
        {"id": 6, "status": "Completed", "duration_minutes": Decimal("42.5")},
        {"id": 3, "ended_at": utc(2026, 1, 12, 15, 42, 30), "duration_minutes": Decimal("42.5")},
    )

    database.complete_run_changeover(6, "Liam", None, utc(2026, 1, 12, 15, 42, 30))

    changeover_update, changeover_params = query_containing(connection, "UPDATE public.changeovers")[0]
    planned_update, planned_params = query_containing(connection, "UPDATE public.planned_downtime_events")[0]
    assert "status = 'Open'" in changeover_update
    assert "ended_at IS NULL" in planned_update
    assert changeover_params["duration_minutes"] == Decimal("42.5000")
    assert planned_params["duration_minutes"] == Decimal("42.5000")
    assert planned_params["id"] == 3
    assert connection.committed


def test_complete_changeover_rolls_back_when_its_planned_stop_already_ended(script):
    connection = script(
        open_changeover_row(),
        {"id": 6, "status": "Completed"},
        None,  # planned stop already ended
    )

    with pytest.raises(PulseCaptureError) as error:
        database.complete_run_changeover(6, "Liam", None, utc(2026, 1, 12, 15, 42, 30))

    assert error.value.status_code == 409
    assert connection.rolled_back and not connection.committed


@pytest.mark.parametrize(
    "row, status",
    [
        (None, 404),
        (open_changeover_row(status="Completed"), 409),
        (open_changeover_row(started_at=utc(2026, 1, 12, 16)), 409),
    ],
)
def test_complete_changeover_rejections(script, row, status):
    connection = script(row)

    with pytest.raises(PulseCaptureError) as error:
        database.complete_run_changeover(6, "Liam", None, utc(2026, 1, 12, 15, 30))

    assert error.value.status_code == status
    assert connection.rolled_back


def test_list_changeovers_applies_filters_as_bound_parameters(script):
    connection = script([])

    database.list_changeovers({"production_line": "GIC", "customer": "Tesco", "min_duration_minutes": 30})

    query, params = connection.cursor_obj.calls[0]
    assert "co.production_line = %(production_line)s" in query
    assert "lower(trim(co.previous_customer)) = ANY(%(customer_aliases)s)" in query
    assert "NOT ILIKE 'TEST-%%'" in query
    assert params == {"production_line": "GIC", "customer": "Tesco", "customer_aliases": ["tesco"], "min_duration_minutes": 30}


# ==========================================================
# RUN START AND HMI STATE
# ==========================================================


def test_create_production_run_checks_for_an_active_run_in_the_same_transaction(script):
    # active run? no; open line stop? no; handover run: none; open line faults: none.
    connection = script(None, None, None, [], {"id": 31})

    result = database.create_production_run({
        "production_line": "Rovema", "line_technician": "Liam", "shift": "Days", "customer": "Asda",
        "product": "Basmati", "pack_weight_kg": 1.0, "packs_per_case": 8, "pack_type": "Pillow",
        "target_speed_ppm": 120, "cases_per_pallet": 220, "starting_pallets_remaining": 38,
        "pallets_remaining": 38, "previous_run_completed": 0, "format": None,
    })

    assert result["run_id"] == 31
    check, _params = connection.cursor_obj.calls[0]
    assert "status = 'Active'" in check and "FOR UPDATE" in check
    insert, _p = query_containing(connection, "INSERT INTO public.production_runs")[0]
    assert "format" not in insert  # omitted when not supplied
    assert connection.committed


def test_create_production_run_rejects_a_second_active_run(script):
    connection = script({"id": 9})

    with pytest.raises(PulseCaptureError) as error:
        database.create_production_run({"production_line": "Rovema", "format": None})

    assert error.value.status_code == 409
    assert connection.rolled_back


def test_get_hmi_run_state_reads_run_progress_planned_and_faults(script):
    connection = script(
        run_row(),
        {"hourly_update_count": 2, "pallets_recorded": Decimal("7.5"), "expected_packs": Decimal("1008"),
         "last_period_ended_at": utc(2026, 1, 12, 8)},
        [{"id": 3, "ended_at": None}],
        {"id": 6, "status": "Open"},
        [{"opened_at": utc(2026, 1, 12, 7), "resolved_at": None, "production_status": "Ongoing"}],
        [],                                   # speed changes
        [{"hour_start": utc(2026, 1, 12, 6)}],  # reported hours
        [{"downtime_event_id": 2, "acknowledged": True}],  # faults open on the line
    )

    state = database.get_hmi_run_state(5)

    assert state["run"]["id"] == 5
    assert state["hourly"]["pallets_recorded"] == Decimal("7.5")
    assert state["planned"] == [{"id": 3, "ended_at": None}]
    assert state["open_changeover"]["id"] == 6
    assert len(state["faults"]) == 1
    assert state["reported_hours"] == [utc(2026, 1, 12, 6)]
    assert state["line_faults"][0]["downtime_event_id"] == 2
    # Carried faults are read for the LINE, not only this run.
    line_query, _p = query_containing(connection, "pr.production_line = %(production_line)s")[0]
    assert "de.production_status = 'Ongoing'" in line_query
    assert not connection.committed  # read-only


def test_get_hmi_run_state_returns_none_for_an_unknown_run(script):
    script(None)
    assert database.get_hmi_run_state(404) is None


# ==========================================================
# WEEKLY TARGETS
# ==========================================================


def test_upsert_weekly_targets_returns_previous_and_saved_rows(script):
    previous = {"scope": "site", "production_line": None, "target_tonnes": Decimal("90.000")}
    saved = {"scope": "site", "production_line": None, "target_tonnes": Decimal("100.000")}
    connection = script(None, previous, saved, None, None, {"scope": "line", "production_line": "GIC"}, None)

    results = database.upsert_weekly_targets(
        date(2026, 1, 12),
        [
            {"scope": "site", "production_line": None, "target_tonnes": Decimal(100)},
            {"scope": "line", "production_line": "GIC", "target_tonnes": Decimal(40)},
        ],
        "Kuri",
    )

    assert results[0] == (previous, saved)
    assert results[1][0] is None
    upsert = query_containing(connection, "ON CONFLICT")[0][0]
    assert "(week_start, scope, (COALESCE(production_line, '')))" in upsert
    assert connection.committed


# ==========================================================
# DASHBOARD WINDOW READ
# ==========================================================


def test_shift_based_window_selects_by_operational_shift_instance(script):
    connection = script(
        [{"name": "Rovema"}],
        [{"production_run_id": 5, "period_started_at": utc(2026, 1, 12, 13, 30),
          "period_ended_at": utc(2026, 1, 12, 14, 10)}],
        [],            # runs
        {"legacy_count": 2},
        [], [], [], [], [],
    )

    data = database.get_dashboard_window_data(
        utc(2026, 1, 12, 6), utc(2026, 1, 12, 14), "Rovema", shift_based=True
    )

    hourly_query, _p = connection.cursor_obj.calls[1]
    assert "hu.shift_window_start >= %(window_start)s" in hourly_query
    assert "hu.shift_window_start < %(window_end)s" in hourly_query
    # Downtime is fetched across the boundary-crossing period too.
    assert data["attribution_bounds"] == (utc(2026, 1, 12, 6), utc(2026, 1, 12, 14, 10))
    assert data["legacy_hourly_without_timestamp"] == 2


def test_rolling_window_selects_by_period_end_inclusive(script):
    connection = script([{"name": "Rovema"}], [], [], {"legacy_count": 0}, [], [], [], [], [])

    data = database.get_dashboard_window_data(
        utc(2026, 1, 12, 6), utc(2026, 1, 12, 14), None, shift_based=False
    )

    hourly_query, _p = connection.cursor_obj.calls[1]
    assert "hu.period_ended_at > %(window_start)s" in hourly_query
    assert "hu.period_ended_at <= %(window_end)s" in hourly_query
    assert data["attribution_bounds"] == (utc(2026, 1, 12, 6), utc(2026, 1, 12, 14))


def test_window_read_excludes_test_data_in_every_run_linked_query(script):
    connection = script(
        [{"name": "Rovema"}], [], [], {"legacy_count": 0}, [], [], [], [], [], [],
    )

    database.get_dashboard_window_data(utc(2026, 1, 12, 6), utc(2026, 1, 12, 14), "Rovema", True)

    linked = [q for q, _p in connection.cursor_obj.calls if "production_runs AS pr" in q]
    assert len(linked) == 8
    for query in linked:
        assert "pr.production_line NOT ILIKE 'TEST-%%'" in query
        assert "pr.production_line = %(production_line)s" in query


def test_a_new_run_cannot_start_while_an_other_stop_is_unresolved(script):
    connection = script(None, stoppage_row(kind="other", reason="Power cut"))

    with pytest.raises(PulseCaptureError) as error:
        database.create_production_run(NEW_RUN)

    assert error.value.status_code == 409
    assert "Resolve" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.production_runs")


def test_incoming_start_run_stops_the_handover_at_the_run_start_with_both_technicians(script):
    handover = stoppage_row(kind="handover", started_by="Liam", started_at=utc(2026, 1, 12, 13, 55))
    connection = script(
        None, handover, ENDED_RUN, [],               # ready: handover may be open
        {"id": 31, "started_at": utc(2026, 1, 12, 14, 7)},
        None,                                         # handover closed
        [],                                           # no ended stops to link
    )

    database.create_production_run({**NEW_RUN, "line_technician": "Ben"})

    insert_sql, _p = query_containing(connection, "INSERT INTO public.production_runs")[0]
    assert "RETURNING id, started_at" in insert_sql   # the handover closes at this exact instant
    close_sql, close = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert "ended_at IS NULL" in close_sql
    assert close["ended_at"] == utc(2026, 1, 12, 14, 7)   # exactly the new run's start
    assert close["ended_by"] == "Ben"                      # incoming technician
    assert close["duration"] == Decimal("12.0000")
    assert close["run_id"] == 31
    assert not query_containing(connection, "UPDATE public.changeovers")
    assert connection.committed


def test_changeover_ends_when_the_new_run_starts_and_qa_gets_the_total(script):
    changeover = stoppage_row(
        started_at=utc(2026, 1, 12, 13, 42),
        physical_ended_at=utc(2026, 1, 12, 14, 5), physical_ended_by="Liam",
    )
    connection = script(
        None, changeover, ENDED_RUN, [],
        {"id": 31, "started_at": utc(2026, 1, 12, 14, 12)},
        None,          # changeover stop closed
        None,          # QA record completed
        [],            # no ended stops to link
    )

    database.create_production_run(NEW_RUN)

    _q, close = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert close["ended_at"] == utc(2026, 1, 12, 14, 12)
    assert close["duration"] == Decimal("30.0000")          # 23 min physical + 7 min setup
    co_sql, co = query_containing(connection, "UPDATE public.changeovers")[0]
    assert "status = 'Completed'" in co_sql
    assert co["duration"] == Decimal("30.0000") and co["product"] == "Jasmine"


def test_a_late_choice_starts_when_the_run_ended_even_days_before(script):
    """The decision has no time limit: made two days later, the event
    still covers the whole gap from the run's end."""
    connection = script(None, None, ENDED_RUN, None, stoppage_row(kind="handover"))

    database.start_line_stoppage("Rovema", "handover", None, "Ben", utc(2026, 1, 14, 9, 0))

    _q, params = query_containing(connection, "INSERT INTO public.line_stoppages")[0]
    assert params["started_at"] == ENDED_RUN["finished_at"]


def test_only_one_next_step_is_recorded_per_ended_run(script):
    """A second tap - or a different choice from another tablet - after
    the first succeeded adds nothing."""
    connection = script(None, None, ENDED_RUN, {"state": "recorded"})

    with pytest.raises(PulseCaptureError) as error:
        database.start_line_stoppage("Rovema", "handover", None, "Liam", utc(2026, 1, 12, 13, 42))

    assert error.value.status_code == 409
    assert "already been recorded" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.line_stoppages")


def test_resolving_other_starts_a_restart_delay_at_the_same_instant(script):
    other = stoppage_row(kind="other", reason="Power cut")
    resolved = {**other, "ended_at": utc(2026, 1, 12, 14, 5), "ended_by": "Ben", "duration_minutes": Decimal(23)}
    delay = stoppage_row(kind="restart_delay", reason="Power cut", started_by="Ben",
                         started_at=utc(2026, 1, 12, 14, 5))
    connection = script(other, resolved, delay)

    result = database.end_line_stoppage(11, "Ben", utc(2026, 1, 12, 14, 5))

    insert, params = query_containing(connection, "INSERT INTO public.line_stoppages")[0]
    assert "'restart_delay'" in insert
    assert params["started_at"] == utc(2026, 1, 12, 14, 5)   # no gap, no overlap
    assert params["started_by"] == "Ben" and params["previous_run_id"] == 5
    assert params["follows_id"] == 11                         # linked to its Other, not guessed by time
    assert result["restart_delay"]["kind"] == "restart_delay"
    assert connection.committed                                # one transaction


def test_a_repeated_resolve_tap_adds_no_second_restart_delay(script):
    resolved = stoppage_row(kind="other", reason="Power cut", ended_at=utc(2026, 1, 12, 14, 5),
                            ended_by="Ben", duration_minutes=Decimal(23))
    delay = stoppage_row(kind="restart_delay", reason="Power cut", started_at=utc(2026, 1, 12, 14, 5))
    connection = script(resolved, delay)

    result = database.end_line_stoppage(11, "Ben", utc(2026, 1, 12, 14, 7))

    assert query_containing(connection, "WHERE follows_stoppage_id = %(id)s")
    assert not query_containing(connection, "INSERT INTO public.line_stoppages")
    assert not query_containing(connection, "UPDATE public.line_stoppages")
    assert result["stoppage"]["ended_at"] == utc(2026, 1, 12, 14, 5)
    assert result["restart_delay"]["id"] == delay["id"]


def test_a_restart_delay_is_only_ended_by_the_next_run(script):
    connection = script(stoppage_row(kind="restart_delay", reason="Power cut"))

    with pytest.raises(PulseCaptureError) as error:
        database.end_line_stoppage(11, "Ben", utc(2026, 1, 12, 14, 20))

    assert error.value.status_code == 409
    assert connection.rolled_back


def test_the_next_run_stops_the_restart_delay_at_its_start(script):
    delay = stoppage_row(kind="restart_delay", reason="Power cut", started_at=utc(2026, 1, 12, 14, 5))
    connection = script(
        None, delay, ENDED_RUN, [],
        {"id": 31, "started_at": utc(2026, 1, 12, 14, 30)},
        None,          # restart delay closed
        [],            # ended Other stop linked
    )

    database.create_production_run({**NEW_RUN, "line_technician": "Ben"})

    _q, close = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert close["ended_at"] == utc(2026, 1, 12, 14, 30) and close["duration"] == Decimal("25.0000")
    assert not query_containing(connection, "UPDATE public.changeovers")
    assert connection.committed


def test_two_tablets_choosing_at_once_get_a_clear_refusal(script, monkeypatch):
    connection = script(None, None, ENDED_RUN, None)
    original = connection.cursor_obj.execute

    def execute(query, params=None):
        if "INSERT INTO public.line_stoppages" in query:
            raise database.psycopg.errors.UniqueViolation("uq_line_stoppages_one_next_step_per_run")
        return original(query, params)

    monkeypatch.setattr(connection.cursor_obj, "execute", execute)

    with pytest.raises(PulseCaptureError) as error:
        database.start_line_stoppage("Rovema", "other", "Power cut", "Ben", utc(2026, 1, 12, 13, 42))

    assert error.value.status_code == 409
    assert "already been recorded" in error.value.message


def test_line_state_keeps_an_unresolved_decision_with_no_time_limit(script):
    connection = script([])

    database.get_hmi_line_state()

    query = connection.cursor_obj.calls[0][0]
    assert "awaiting_next_step" in query
    assert "interval" not in query


# ---------------------------------------------------------------
# Legacy baseline (runs that ended before migration 0004)
# ---------------------------------------------------------------


def test_a_legacy_run_does_not_block_start_run_and_nothing_is_fabricated(script):
    connection = script(
        None, None, ENDED_RUN, {"state": "legacy"}, [],
        {"id": 31, "started_at": utc(2026, 1, 12, 14, 0)},
        [],
    )

    result = database.create_production_run(NEW_RUN)

    assert result["run_id"] == 31
    state_sql, _p = query_containing(connection, "run_next_step_legacy_baseline")[0]
    assert "THEN 'legacy'" in state_sql
    assert not query_containing(connection, "INSERT INTO public.line_stoppages")
    assert connection.committed


def test_no_next_step_is_recorded_after_a_legacy_run(script):
    connection = script(None, None, ENDED_RUN, {"state": "legacy"})

    with pytest.raises(PulseCaptureError) as error:
        database.start_line_stoppage("Rovema", "other", "Power cut", "Liam", utc(2026, 1, 12, 13, 42))

    assert error.value.status_code == 409
    assert "ended before the End Run next-step workflow started" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.line_stoppages")


def test_line_state_never_asks_for_a_choice_after_a_legacy_run(script):
    connection = script([])

    database.get_hmi_line_state()

    query = connection.cursor_obj.calls[0][0]
    assert "public.run_next_step_legacy_baseline AS b" in query


# ---------------------------------------------------------------
# Not scheduled
# ---------------------------------------------------------------


def test_not_scheduled_starts_when_the_run_ended_and_opens_no_qa_record(script):
    connection = script(None, None, ENDED_RUN, {"state": None}, stoppage_row(kind="not_scheduled"))

    database.start_line_stoppage("Rovema", "not_scheduled", None, "Liam", utc(2026, 1, 13, 5, 0))

    _q, params = query_containing(connection, "INSERT INTO public.line_stoppages")[0]
    assert params["kind"] == "not_scheduled"
    assert params["started_at"] == ENDED_RUN["finished_at"]
    assert not query_containing(connection, "INSERT INTO public.changeovers")


def test_the_next_run_ends_not_scheduled_time_at_its_start(script):
    stop = stoppage_row(kind="not_scheduled", started_at=utc(2026, 1, 12, 13, 40))
    connection = script(
        None, stop, ENDED_RUN, [],
        {"id": 31, "started_at": utc(2026, 1, 13, 6, 0)},
        None,
        [],
    )

    database.create_production_run(NEW_RUN)

    _q, close = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert close["ended_at"] == utc(2026, 1, 13, 6, 0)
    assert close["ended_by"] == NEW_RUN["line_technician"]


def test_not_scheduled_time_cannot_be_ended_by_hand(script):
    connection = script(stoppage_row(kind="not_scheduled"))

    with pytest.raises(PulseCaptureError) as error:
        database.end_line_stoppage(11, "Ben", utc(2026, 1, 12, 14, 20))

    assert error.value.status_code == 409
    assert connection.rolled_back


# ---------------------------------------------------------------
# Manager reclassification (audit trail)
# ---------------------------------------------------------------

AUDIT = {
    "id": 3, "line_stoppage_id": 11, "previous_kind": "other", "previous_reason": "No orders",
    "new_kind": "not_scheduled", "new_reason": None, "changed_by": "Priya",
    "changed_at": utc(2026, 1, 13, 9, 0), "note": "Line was not on the plan overnight",
}


def test_a_manager_reclassifies_other_as_not_scheduled_with_an_audit_row(script):
    other = stoppage_row(kind="other", reason="No orders")
    connection = script(other, None, stoppage_row(kind="not_scheduled"), AUDIT)

    result = database.reclassify_line_stoppage(
        11, "not_scheduled", None, "Priya", "Line was not on the plan overnight", utc(2026, 1, 13, 9, 0)
    )

    update, params = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert params == {"id": 11, "kind": "not_scheduled", "reason": None}
    set_clause = update.split("SET", 1)[1].split("WHERE", 1)[0]
    assert "started_at" not in set_clause and "ended_at" not in set_clause   # same interval, never moved
    _q, audit = query_containing(connection, "INSERT INTO public.line_stoppage_reclassifications")[0]
    assert audit["previous_kind"] == "other" and audit["previous_reason"] == "No orders"
    assert audit["new_kind"] == "not_scheduled" and audit["changed_by"] == "Priya"
    assert audit["changed_at"] == utc(2026, 1, 13, 9, 0)
    assert audit["note"] == "Line was not on the plan overnight"
    assert result["reclassification"]["id"] == 3
    assert connection.committed


def test_a_changeover_is_not_reclassified(script):
    connection = script(stoppage_row(kind="changeover"), None)

    with pytest.raises(PulseCaptureError) as error:
        database.reclassify_line_stoppage(11, "not_scheduled", None, "Priya", "why", utc(2026, 1, 13, 9))

    assert error.value.status_code == 409
    assert not query_containing(connection, "UPDATE public.line_stoppages")


def test_a_resolved_other_with_a_restart_delay_only_takes_a_reason_correction(script):
    other = stoppage_row(kind="other", reason="Power cut", ended_at=utc(2026, 1, 12, 14, 0), ended_by="Ben",
                         duration_minutes=Decimal(20))
    connection = script(other, stoppage_row(id=12, kind="restart_delay", follows_stoppage_id=11))

    with pytest.raises(PulseCaptureError) as error:
        database.reclassify_line_stoppage(11, "not_scheduled", None, "Priya", "why", utc(2026, 1, 13, 9))

    assert error.value.status_code == 409
    assert "reclassify the Restart delay" in error.value.message
    assert not query_containing(connection, "INSERT INTO public.line_stoppage_reclassifications")


def test_a_restart_delay_can_become_not_scheduled_and_back_with_its_other_reason(script):
    delay = stoppage_row(id=12, kind="not_scheduled", reason=None, follows_stoppage_id=11)
    connection = script(
        delay, None,
        {"reason": "Power cut"},                                 # the Other it follows
        stoppage_row(id=12, kind="restart_delay", reason="Power cut", follows_stoppage_id=11),
        {**AUDIT, "new_kind": "restart_delay"},
    )

    database.reclassify_line_stoppage(12, "restart_delay", None, "Priya", "Was a real restart delay", utc(2026, 1, 13, 9))

    _q, params = query_containing(connection, "UPDATE public.line_stoppages")[0]
    assert params == {"id": 12, "kind": "restart_delay", "reason": "Power cut"}


def test_reclassifying_to_the_same_classification_changes_nothing(script):
    connection = script(stoppage_row(kind="not_scheduled", reason=None), None)

    with pytest.raises(PulseCaptureError) as error:
        database.reclassify_line_stoppage(11, "not_scheduled", None, "Priya", "why", utc(2026, 1, 13, 9))

    assert error.value.status_code == 409
    assert not query_containing(connection, "UPDATE public.line_stoppages")


def test_a_missing_line_stop_is_404(script):
    script(None)
    with pytest.raises(PulseCaptureError) as error:
        database.reclassify_line_stoppage(99, "not_scheduled", None, "Priya", "why", utc(2026, 1, 13, 9))
    assert error.value.status_code == 404


# ==========================================================
# MANAGER FORCE-CLOSE
# ==========================================================


def test_force_close_returns_none_when_the_run_is_no_longer_active(script):
    connection = script(None)

    assert database.force_close_production_run(5, utc(2026, 1, 12, 9), "Kuri (manager force-close)") is None
    assert connection.rolled_back and not connection.committed


def test_force_close_refuses_an_open_changeover_and_changes_nothing(script):
    connection = script({"id": 5, "production_line": "Rovema", "status": "Active"}, {"id": 3})

    with pytest.raises(PulseCaptureError) as error:
        database.force_close_production_run(5, utc(2026, 1, 12, 9), "Kuri (manager force-close)")

    assert error.value.status_code == 409
    assert "Changeover Complete" in error.value.message
    assert connection.rolled_back and not connection.committed
    assert not query_containing(connection, "UPDATE public.production_runs")


def test_force_close_ends_an_open_planned_stop_at_the_close_time(script):
    closed_at = utc(2026, 1, 12, 9)
    open_stop = {
        "id": 8, "production_run_id": 5, "production_line": "Rovema", "reason": "Break",
        "started_by": "Liam", "started_at": utc(2026, 1, 12, 8, 30), "ended_by": None,
        "ended_at": None, "duration_minutes": None,
    }
    connection = script(
        {"id": 5, "production_line": "Rovema", "status": "Active"},
        None,
        open_stop,
        {**open_stop, "ended_at": closed_at, "ended_by": "Kuri (manager force-close)",
         "duration_minutes": Decimal("30")},
        {"id": 5, "production_line": "Rovema", "status": "Cancelled", "finished_at": closed_at},
    )

    closed = database.force_close_production_run(5, closed_at, "Kuri (manager force-close)")

    assert connection.committed
    assert closed["status"] == "Cancelled"
    assert closed["ended_planned_stop"]["reason"] == "Break"
    (_query, params), = query_containing(connection, "UPDATE public.planned_downtime_events")
    assert params["ended_at"] == closed_at
    assert params["duration_minutes"] == Decimal("30")
    # No output is invented for the hours nobody reported.
    assert not query_containing(connection, "hourly_updates")


def test_force_close_without_open_stops_only_closes_the_run(script):
    closed_at = utc(2026, 1, 12, 9)
    connection = script(
        {"id": 5, "production_line": "Rovema", "status": "Active"},
        None,
        None,
        {"id": 5, "production_line": "Rovema", "status": "Cancelled", "finished_at": closed_at},
    )

    closed = database.force_close_production_run(5, closed_at, "Kuri (manager force-close)")

    assert connection.committed
    assert closed["ended_planned_stop"] is None
    assert not query_containing(connection, "UPDATE public.planned_downtime_events")
    assert not query_containing(connection, "hourly_updates")
    assert "FOR UPDATE" in connection.cursor_obj.calls[0][0]


def test_self_resolved_stop_records_actual_interval_without_engineering_call(script):
    start, restart = utc(2026, 1, 12, 7, 10), utc(2026, 1, 12, 7, 15)
    connection = script(run_row(), {"next_fault_id": 1}, {"id": 41})
    database.report_fault_to_engineering(5, {"machine": "BV1", "reason": "Film jam", "reported_by": "Liam",
        "note": "Removed trapped film", "outcome": "resolved", "started_at": start, "restored_at": restart}, utc(2026, 1, 12, 8))
    query, params = query_containing(connection, "INSERT INTO public.downtime_events")[0]
    assert params["opened_at"] == start
    assert params["resolved_at"] == restart
    assert params["production_status"] == "Resolved"
    assert params["engineer_called"] is False
    assert params["retrospective"] is True
    assert connection.committed


@pytest.mark.parametrize("start,restart", [(utc(2026,1,12,5), utc(2026,1,12,7)), (utc(2026,1,12,7), utc(2026,1,12,9))])
def test_self_resolved_stop_rejects_outside_run_or_future_times(script, start, restart):
    connection = script(run_row())
    with pytest.raises(PulseCaptureError):
        database.report_fault_to_engineering(5, {"machine": "BV1", "reason": "Jam", "reported_by": "Liam",
            "note": "Cleared", "outcome": "resolved", "started_at": start, "restored_at": restart}, utc(2026,1,12,8))
    assert not connection.committed


def test_force_close_audit_failure_prevents_commit(script):
    closed_at=utc(2026,1,12,9)
    connection=script({"id":5,"production_line":"Rovema","status":"Active"},None,None,
        {"id":5,"production_line":"Rovema","status":"Cancelled","finished_at":closed_at},RuntimeError("audit unavailable"))
    with pytest.raises(RuntimeError,match="audit unavailable"):
        database.force_close_production_run(5,closed_at,"Kuri",reason="Production stopped",manager_name="Kuri")
    assert not connection.committed


def test_force_close_audit_contains_locked_state_actor_and_reason(script):
    closed_at=utc(2026,1,12,9)
    connection=script({"id":5,"production_line":"Rovema","status":"Active"},None,None,
        {"id":5,"production_line":"Rovema","status":"Cancelled","finished_at":closed_at})
    database.force_close_production_run(5,closed_at,"Kuri",reason="Production stopped",manager_name="Kuri")
    _,params=query_containing(connection,"INSERT INTO public.management_audit_log")[0]
    assert params['manager']=='Kuri' and params['reason']=='Production stopped'
    assert params['before'].obj['status']=='Active' and params['after'].obj['status']=='Cancelled'
    assert connection.committed


@pytest.mark.parametrize('function,args',[
 (database.create_production_line,('Audit line',)),
 (database.create_machine,(1,'Audit machine')),
 (database.create_button,(1,'Audit reason','unplanned_fault','Production')),
])
def test_configuration_creation_audit_failure_prevents_commit(script,function,args):
    connection=script({'id':21},RuntimeError('Audit failed'))
    with pytest.raises(RuntimeError,match='Audit failed'):
        function(*args,audit_actor='Kuri')
    assert not connection.committed


@pytest.mark.parametrize('function,args',[
 (database.update_production_line,(1,)),(database.update_machine,(1,)),(database.update_button,(1,)),
])
def test_configuration_update_audits_locked_before_and_after(script,function,args):
    connection=script({'id':1,'name':'Before'},{'id':1,'name':'After'})
    function(*args,name='After',audit_actor='Kuri')
    assert 'FOR UPDATE' in connection.cursor_obj.calls[0][0]
    _,params=query_containing(connection,'INSERT INTO public.management_audit_log')[0]
    assert params[1]=='Kuri' and params[4].obj['name']=='Before' and params[5].obj['name']=='After'
    assert connection.committed
