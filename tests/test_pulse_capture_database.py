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
        {"last_end": utc(2026, 1, 12, 7)},
        [],
        {"id": 77},
        {"id": 5},
        None,  # store response
    )

    database.record_hourly_update(
        5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8),
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
            5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
            5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
            5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
        {"last_end": utc(2026, 1, 12, 7)},
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
        {"last_end": utc(2026, 1, 12, 7)},
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
        {"last_end": utc(2026, 1, 12, 7)},
        [],
        {"id": 78},
        {"id": 5},
        None,
    )

    saved = database.record_hourly_update(
        5, Decimal("1.25"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
            5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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
        {"last_end": utc(2026, 1, 12, 7)},
        [],
        {"id": 77},
        {"id": 5},
        None,
    )

    database.record_hourly_update(
        5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8), idempotency=idempotency()
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


def test_record_hourly_update_persists_decimal_pallets_and_progress(script):
    connection = script(
        run_row(),
        {"last_end": utc(2026, 1, 12, 7)},
        [{"reason": "Film Change", "started_at": utc(2026, 1, 12, 7, 30), "ended_at": utc(2026, 1, 12, 7, 40)}],
        {"id": 77},
        {"id": 5},
    )

    saved = database.record_hourly_update(5, Decimal("3.75"), "Liam", None, utc(2026, 1, 12, 8))

    assert connection.committed and not connection.rolled_back
    assert "FOR UPDATE" in connection.cursor_obj.calls[0][0]

    insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["pallets_completed"] == Decimal("3.7500")
    assert params["expected_packs"] == Decimal("504.0000")
    assert params["planned_downtime_minutes"] == Decimal("10.0000")
    assert params["planned_downtime"] == "Film Change"
    assert params["period_started_at"] == utc(2026, 1, 12, 7)
    assert params["recorded_at"] == utc(2026, 1, 12, 8)
    assert "'react_hmi'" in insert

    _update, progress = query_containing(connection, "UPDATE public.production_runs")[0]
    assert progress["pallets_remaining"] == Decimal("21.2500")
    assert progress["total_pallets_completed"] == Decimal("3.7500")
    assert saved["hourly_update_id"] == 77


def test_first_hourly_update_period_starts_at_run_start(script):
    connection = script(run_row(), {"last_end": None}, [], {"id": 1}, {"id": 5})

    database.record_hourly_update(5, Decimal(5), "Liam", None, utc(2026, 1, 12, 7, 15))

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["period_started_at"] == utc(2026, 1, 12, 6)
    assert params["period_minutes"] == Decimal("75.0000")
    assert params["expected_packs"] == Decimal("630.0000")
    assert params["planned_downtime"] == "None"


def test_two_updates_in_quick_succession_are_both_accepted(script):
    # Only a zero-length period is refused - "within five minutes" is
    # NOT treated as a duplicate; that is the Idempotency-Key's job.
    connection = script(run_row(), {"last_end": utc(2026, 1, 12, 7, 58)}, [], {"id": 2}, {"id": 5})

    database.record_hourly_update(5, Decimal(1), "Liam", None, utc(2026, 1, 12, 8))

    assert connection.committed
    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["period_minutes"] == Decimal("2.0000")


def test_zero_length_period_is_rejected_and_rolled_back(script):
    connection = script(run_row(), {"last_end": utc(2026, 1, 12, 8)})

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, Decimal(1), "Liam", None, utc(2026, 1, 12, 8))

    assert error.value.status_code == 409
    assert connection.rolled_back and not connection.committed
    assert not query_containing(connection, "INSERT INTO public.hourly_updates")


@pytest.mark.parametrize("run, status", [(None, 404), (run_row(status="Completed"), 409)])
def test_hourly_update_requires_an_existing_active_run(script, run, status):
    connection = script(run)

    with pytest.raises(PulseCaptureError) as error:
        database.record_hourly_update(5, Decimal(1), "Liam", None, utc(2026, 1, 12, 8))

    assert error.value.status_code == status
    assert connection.rolled_back


# ==========================================================
# SHIFT ATTRIBUTION (all three boundaries)
# ==========================================================


@pytest.mark.parametrize(
    "shift, period_start, period_end, expected_window_start",
    [
        # A period ending exactly ON each boundary stays with the shift
        # that produced it, not the one starting at that moment.
        ("Days", utc(2026, 1, 12, 13), utc(2026, 1, 12, 14), utc(2026, 1, 12, 6)),
        ("Afternoons", utc(2026, 1, 12, 21), utc(2026, 1, 12, 22), utc(2026, 1, 12, 14)),
        ("Nights", utc(2026, 1, 12, 5), utc(2026, 1, 12, 6), utc(2026, 1, 11, 22)),
        # A period CROSSING a boundary also stays with the run's shift.
        ("Days", utc(2026, 1, 12, 13, 30), utc(2026, 1, 12, 14, 10), utc(2026, 1, 12, 6)),
        ("Afternoons", utc(2026, 1, 12, 21, 30), utc(2026, 1, 12, 22, 20), utc(2026, 1, 12, 14)),
        ("Nights", utc(2026, 1, 12, 5, 30), utc(2026, 1, 12, 6, 10), utc(2026, 1, 11, 22)),
        # British Summer Time: 06:00 London is 05:00 UTC.
        ("Days", utc(2026, 7, 13, 12), utc(2026, 7, 13, 13), utc(2026, 7, 13, 5)),
    ],
)
def test_hourly_output_stays_with_the_runs_recorded_shift(
    script, shift, period_start, period_end, expected_window_start
):
    connection = script(
        run_row(shift=shift, started_at=period_start),
        {"last_end": period_start},
        [],
        {"id": 9},
        {"id": 5},
    )

    database.record_hourly_update(5, Decimal(1), "Liam", None, period_end)

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["shift"] == {"Days": "Day", "Afternoons": "Afternoon", "Nights": "Night"}[shift]
    assert params["shift_window_start"] == expected_window_start
    assert params["period_started_at"] == period_start
    assert params["recorded_at"] == period_end


def test_unrecognised_legacy_shift_label_falls_back_to_the_clock(script):
    connection = script(
        run_row(shift="Twilight"), {"last_end": utc(2026, 1, 12, 9)}, [], {"id": 9}, {"id": 5}
    )

    database.record_hourly_update(5, Decimal(1), "Liam", None, utc(2026, 1, 12, 10))

    _insert, params = query_containing(connection, "INSERT INTO public.hourly_updates")[0]
    assert params["shift"] == "Day"
    assert params["shift_window_start"] == utc(2026, 1, 12, 6)


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
    assert "'Ongoing'" in insert
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
        # final hourly update
        {"last_end": utc(2026, 1, 12, 13)},
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
        {"last_end": utc(2026, 1, 12, 13)},
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
        run_row(), {"covered_to": None},
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
    assert "(co.previous_customer = %(customer)s OR co.new_customer = %(customer)s)" in query
    assert "NOT ILIKE 'TEST-%%'" in query
    assert params == {"production_line": "GIC", "customer": "Tesco", "min_duration_minutes": 30}


# ==========================================================
# RUN START AND HMI STATE
# ==========================================================


def test_create_production_run_checks_for_an_active_run_in_the_same_transaction(script):
    connection = script(None, {"id": 31})

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
    )

    state = database.get_hmi_run_state(5)

    assert state["run"]["id"] == 5
    assert state["hourly"]["pallets_recorded"] == Decimal("7.5")
    assert state["planned"] == [{"id": 3, "ended_at": None}]
    assert state["open_changeover"]["id"] == 6
    assert len(state["faults"]) == 1
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
    connection = script(previous, saved, None, {"scope": "line", "production_line": "GIC"})

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
        [{"name": "Rovema"}], [], [], {"legacy_count": 0}, [], [], [], [], [],
    )

    database.get_dashboard_window_data(utc(2026, 1, 12, 6), utc(2026, 1, 12, 14), "Rovema", True)

    linked = [q for q, _p in connection.cursor_obj.calls if "production_runs AS pr" in q]
    assert len(linked) == 8
    for query in linked:
        assert "pr.production_line NOT ILIKE 'TEST-%%'" in query
        assert "pr.production_line = %(production_line)s" in query
