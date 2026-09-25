"""
Offline HTTP tests for the HMI capture API (src/pulse_capture_api.py),
composed onto the app in src/api.py.

Never touches Supabase: every src.database function the module imported
is monkeypatched at the point where src/pulse_capture_api.py imported it.
Every write sends an Idempotency-Key (the default header on `client`).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import pulse_calculations as calc
from src import pulse_capture_api as capture
from src.api import app
from src.database import IdempotentReplay, PulseCaptureError


KEY = "capture-test-key-00000000000001"
client = TestClient(app, headers={"Idempotency-Key": KEY})

NOW = datetime(2026, 1, 12, 8, 0, tzinfo=timezone.utc)
SECRET = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"
CONFIG = calc.PackConfig(Decimal("8.4"), Decimal(10), Decimal(10), Decimal("1"))


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(capture, "_now", lambda: NOW)


def run_row(line="Rovema", status="Active"):
    return lambda run_id: {"id": run_id, "production_line": line, "status": status}


def assert_no_secret(response, captured):
    assert SECRET not in response.text
    assert "s3cr3t" not in captured.out + captured.err


def recorder(result_factory):
    calls = []

    def fake(*args, idempotency=None):
        calls.append({"args": args, "idempotency": idempotency})
        return result_factory(*args)

    fake.calls = calls
    return fake


def raising(error):
    def fake(*args, **kwargs):
        raise error

    return fake


WRITE_ROUTES = [
    ("/api/v1/runs/5/hourly-updates", {"line_technician": "Liam", "pallets_produced": "2"}),
    ("/api/v1/runs/5/planned-downtime", {"reason": "Film Change", "started_by": "Liam"}),
    ("/api/v1/planned-downtime/3/end", {"ended_by": "Liam"}),
    ("/api/v1/runs/5/faults", {"reported_by": "Liam", "machine": "BV1", "reason": "Jam", "note": "Stuck"}),
    ("/api/v1/runs/5/xray-counts", {"line_technician": "Liam", "production_since_last_update": False,
                                    "xray_pack_count": 10}),
    ("/api/v1/runs/5/changeovers", {"line_technician": "Liam", "new_customer": "Tesco", "new_product": "Jasmine",
                                    "new_pack_weight_kg": "4", "new_format": "Block"}),
    ("/api/v1/changeovers/6/complete", {"completed_by": "Liam", "first_acceptable_packs_confirmed": True}),
]


@pytest.mark.parametrize("path, body", WRITE_ROUTES)
def test_every_capture_write_requires_an_idempotency_key(path, body, monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    anonymous = TestClient(app)

    response = anonymous.post(path, json=body)

    assert response.status_code == 422


# ==========================================================
# HOURLY UPDATE
# ==========================================================


def saved_hourly(run_id, pallets, *_rest):
    values = calc.hourly_update_values(
        CONFIG, pallets, Decimal(60), Decimal(10),
        {"pallets_remaining": 25, "total_pallets_completed": 0, "potential_overrun_pallets": 0},
    )
    return {
        **values,
        "hourly_update_id": 77,
        "production_run_id": run_id,
        "production_line": "Rovema",
        "period_started_at": NOW - timedelta(hours=1),
        "period_ended_at": NOW,
        "shift": "Day",
        "shift_window_start": datetime(2026, 1, 12, 6, tzinfo=timezone.utc),
        "config": CONFIG,
    }


def test_hourly_update_accepts_decimal_string_and_returns_backend_figures(monkeypatch):
    fake = recorder(saved_hourly)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "3.75"}
    )

    assert response.status_code == 201
    args = fake.calls[0]["args"]
    assert args[1] == Decimal("3.75")
    assert args[4] == NOW
    assert fake.calls[0]["idempotency"].key == KEY
    assert fake.calls[0]["idempotency"].action == "hourly_update:5"

    body = response.json()
    assert body["pallets_produced"] == 3.75
    assert body["expected_packs"] == 504.0
    assert body["actual_packs"] == 375.0
    assert body["production_achievement_percent"] == 74.4
    assert body["pallets_remaining"] == 21.25
    assert body["shift"] == "Day"
    assert body["shift_window_start"] == "2026-01-12T06:00:00+00:00"


def test_zero_pallets_is_a_valid_hourly_update(monkeypatch):
    fake = recorder(saved_hourly)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "0"}
    )

    assert response.status_code == 201
    assert fake.calls[0]["args"][1] == Decimal(0)
    assert response.json()["pallets_produced"] == 0.0


def test_stored_response_is_what_the_client_receives(monkeypatch):
    stored = {}

    def fake(*args, idempotency=None):
        result = saved_hourly(*args)
        stored["pair"] = idempotency.respond(result)
        return result

    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"}
    )

    assert stored["pair"] == (201, response.json())


def test_retry_with_the_same_key_replays_the_original_update(monkeypatch):
    original = {"status": "success", "hourly_update_id": 77, "pallets_produced": 3.75}
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", raising(IdempotentReplay(201, original)))

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "3.75"}
    )

    assert response.status_code == 201
    assert response.json() == original
    assert response.headers["idempotent-replayed"] == "true"


def test_two_different_hourly_updates_are_both_accepted(monkeypatch):
    fake = recorder(saved_hourly)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    first = client.post("/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"},
                        headers={"Idempotency-Key": "hourly-key-aaaaaaaaaaaa01"})
    second = client.post("/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"},
                         headers={"Idempotency-Key": "hourly-key-aaaaaaaaaaaa02"})

    assert first.status_code == second.status_code == 201
    assert len(fake.calls) == 2
    assert fake.calls[0]["idempotency"].key != fake.calls[1]["idempotency"].key


@pytest.mark.parametrize(
    "payload",
    [
        {"line_technician": "Liam", "pallets_produced": "-1"},
        {"line_technician": "Liam", "pallets_produced": "1.23456"},
        {"line_technician": "Liam", "pallets_produced": "1001"},
        {"line_technician": "Liam", "pallets_produced": "NaN"},
        {"line_technician": "Liam", "pallets_produced": "abc"},
        {"line_technician": "   ", "pallets_produced": "2"},
        {"pallets_produced": "2"},
        {"line_technician": "Liam"},
    ],
)
def test_hourly_update_rejects_invalid_input_before_touching_the_database(payload, monkeypatch):
    fake = recorder(saved_hourly)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    response = client.post("/api/v1/runs/5/hourly-updates", json=payload)

    assert response.status_code == 422
    assert fake.calls == []


def test_hourly_update_rejects_unknown_technician(monkeypatch):
    fake = recorder(saved_hourly)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", fake)

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Nobody", "pallets_produced": "2"}
    )

    assert response.status_code == 422
    assert fake.calls == []


def test_hourly_update_unknown_run_is_404(monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", lambda run_id: None)

    response = client.post(
        "/api/v1/runs/404/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "error",
    [
        PulseCaptureError(409, "Production Run 5 is not active."),
        PulseCaptureError(409, "This request was already used with different details."),
        PulseCaptureError(409, "This action is still being processed."),
    ],
)
def test_hourly_update_conflicts_are_safe_409s(error, monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", raising(error))

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == error.message


def test_hourly_update_database_failure_is_safe_503(monkeypatch, capsys):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_hourly_update", raising(RuntimeError(SECRET)))

    response = client.post(
        "/api/v1/runs/5/hourly-updates", json={"line_technician": "Liam", "pallets_produced": "2"}
    )

    assert response.status_code == 503
    assert_no_secret(response, capsys.readouterr())


# ==========================================================
# PLANNED DOWNTIME
# ==========================================================


def planned_row(**overrides):
    row = {
        "id": 3, "production_run_id": 5, "production_line": "Rovema", "reason": "Film Change",
        "started_by": "Liam", "started_at": NOW, "ended_by": None, "ended_at": None,
        "duration_minutes": None,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("reason", ["Label Change", "Film Change", "CCP Check"])
def test_start_planned_downtime_for_each_standard_reason(reason, monkeypatch):
    fake = recorder(lambda run_id, r, by, at: planned_row(reason=r))
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "start_planned_downtime", fake)

    response = client.post("/api/v1/runs/5/planned-downtime", json={"reason": reason, "started_by": "Liam"})

    assert response.status_code == 201
    assert response.json()["reason"] == reason
    assert response.json()["ended_at"] is None
    assert fake.calls[0]["idempotency"].action == "planned_downtime_start:5"


@pytest.mark.parametrize("reason", ["Changeover", "changeover"])
def test_changeover_cannot_be_started_as_a_plain_planned_stop(reason, monkeypatch):
    fake = recorder(lambda *a: planned_row())
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "start_planned_downtime", fake)

    response = client.post("/api/v1/runs/5/planned-downtime", json={"reason": reason, "started_by": "Liam"})

    assert response.status_code == 422
    assert fake.calls == []


def test_second_open_planned_downtime_is_409(monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(
        capture, "start_planned_downtime",
        raising(PulseCaptureError(409, "Planned downtime is already in progress for this run.")),
    )

    response = client.post("/api/v1/runs/5/planned-downtime", json={"reason": "Film Change", "started_by": "Liam"})

    assert response.status_code == 409


def test_end_planned_downtime_returns_backend_duration(monkeypatch):
    ended = planned_row(ended_by="Liam", ended_at=NOW, duration_minutes=Decimal("12.5000"))
    fake = recorder(lambda event_id, by, at: ended)
    monkeypatch.setattr(capture, "end_planned_downtime", fake)

    response = client.post("/api/v1/planned-downtime/3/end", json={"ended_by": "Liam"})

    assert response.status_code == 200
    assert response.json()["duration_minutes"] == 12.5
    assert fake.calls[0]["idempotency"].action == "planned_downtime_end:3"


def test_end_planned_downtime_retry_replays(monkeypatch):
    original = {"status": "success", "planned_downtime_id": 3, "duration_minutes": 12.5}
    monkeypatch.setattr(capture, "end_planned_downtime", raising(IdempotentReplay(200, original)))

    response = client.post("/api/v1/planned-downtime/3/end", json={"ended_by": "Liam"})

    assert response.status_code == 200
    assert response.json() == original


def test_changeover_stop_cannot_be_ended_as_plain_planned_downtime(monkeypatch):
    monkeypatch.setattr(
        capture, "end_planned_downtime",
        raising(PulseCaptureError(409, "This planned stop belongs to a changeover.")),
    )

    response = client.post("/api/v1/planned-downtime/3/end", json={"ended_by": "Liam"})

    assert response.status_code == 409


@pytest.mark.parametrize("error, status", [(PulseCaptureError(404, "missing"), 404), (RuntimeError(SECRET), 503)])
def test_end_planned_downtime_failures(error, status, monkeypatch):
    monkeypatch.setattr(capture, "end_planned_downtime", raising(error))

    response = client.post("/api/v1/planned-downtime/99/end", json={"ended_by": "Liam"})

    assert response.status_code == status
    assert "s3cr3t" not in response.text


def test_end_planned_downtime_rejects_unknown_person(monkeypatch):
    fake = recorder(lambda *a: planned_row())
    monkeypatch.setattr(capture, "end_planned_downtime", fake)

    response = client.post("/api/v1/planned-downtime/3/end", json={"ended_by": "Nobody"})

    assert response.status_code == 422
    assert fake.calls == []


# ==========================================================
# REPORT TO ENGINEER
# ==========================================================


def created_fault(run_id, report, opened_at):
    return {
        "id": 41, "production_run_id": run_id, "production_line": "Rovema", "fault_id": 4,
        "machine": "BV1", "reason": "Film Jam", "reported_by": "Liam",
        "production_status": "Ongoing", "engineering_status": "Not Started", "opened_at": opened_at,
    }


def test_report_fault_with_configured_machine_and_button(monkeypatch):
    fake = recorder(created_fault)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "report_fault_to_engineering", fake)

    response = client.post(
        "/api/v1/runs/5/faults",
        json={"reported_by": "Liam", "machine": "BV1", "reason": "Film Jam", "machine_id": 7, "button_id": 12},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["downtime_event_id"] == 41
    assert body["production_status"] == "Ongoing"
    assert body["engineering_status"] == "Not Started"
    report = fake.calls[0]["args"][1]
    assert report["machine_id"] == 7 and report["button_id"] == 12
    assert fake.calls[0]["idempotency"].action == "fault_report:5"


def test_report_fault_without_a_configured_button_requires_a_note(monkeypatch):
    fake = recorder(created_fault)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "report_fault_to_engineering", fake)

    missing = client.post("/api/v1/runs/5/faults", json={"reported_by": "Liam", "machine": "BV1", "reason": "Other"})
    blank = client.post("/api/v1/runs/5/faults",
                        json={"reported_by": "Liam", "machine": "BV1", "reason": "Other", "note": "   "})
    ok = client.post("/api/v1/runs/5/faults",
                     json={"reported_by": "Liam", "machine": "BV1", "reason": "Other", "note": "Sensor loose"})

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert ok.status_code == 201
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"reported_by": "Liam", "machine": "BV1", "reason": "Film Jam", "button_id": 12},
        {"reported_by": "Liam", "machine": "BV1", "reason": "  ", "note": "x"},
        {"reported_by": "Liam", "machine": "", "reason": "Film Jam", "note": "x"},
        {"reported_by": "Nobody", "machine": "BV1", "reason": "Film Jam", "note": "x"},
    ],
)
def test_report_fault_validation(payload, monkeypatch):
    fake = recorder(created_fault)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "report_fault_to_engineering", fake)

    response = client.post("/api/v1/runs/5/faults", json=payload)

    assert response.status_code == 422
    assert fake.calls == []


def test_repeated_fault_report_replays_the_same_fault(monkeypatch):
    original = {"status": "success", "downtime_event_id": 41, "fault_id": 4}
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "report_fault_to_engineering", raising(IdempotentReplay(201, original)))

    response = client.post(
        "/api/v1/runs/5/faults",
        json={"reported_by": "Liam", "machine": "BV1", "reason": "Film Jam", "machine_id": 7, "button_id": 12},
    )

    assert response.status_code == 201
    assert response.json()["downtime_event_id"] == 41


def test_report_fault_machine_from_another_line_is_422(monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(
        capture, "report_fault_to_engineering",
        raising(PulseCaptureError(422, "That machine is not an active machine on this production line.")),
    )

    response = client.post(
        "/api/v1/runs/5/faults",
        json={"reported_by": "Liam", "machine": "BV1", "reason": "Film Jam", "machine_id": 999, "note": "x"},
    )

    assert response.status_code == 422


# ==========================================================
# END-OF-SHIFT X-RAY COUNT AND COMPLETION PREVIEW
# ==========================================================


def saved_xray(run_id, capture_dict, *_rest, **overrides):
    saved = {
        "xray_capture_id": 8, "captured_at": NOW, "capture_point": "shift_end",
        "production_run_id": run_id, "production_line": "Rovema", "shift": "Day",
        "count_available": capture_dict["count_available"],
        "xray_pack_count": capture_dict["xray_pack_count"],
        "unavailable_reason": capture_dict["unavailable_reason"],
        "final_hourly_update": None, "total_pallets_recorded": Decimal("8.75"),
        "palletised_pallets": Decimal("8.75"), "palletised_packs": Decimal("875"),
        "pallets_remaining": Decimal("16.25"), "total_pallets_completed": Decimal("8.75"),
        "potential_overrun_pallets": Decimal(0), "waste_status": "estimated",
        "post_xray_pack_difference": Decimal(125), "estimated_post_xray_waste_percent": Decimal("12.5"),
        "warning": None,
    }
    saved.update(overrides)
    return saved


def test_shift_end_xray_count_available(monkeypatch):
    fake = recorder(saved_xray)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_xray_capture", fake)

    response = client.post(
        "/api/v1/runs/5/xray-counts",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 1000},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["estimated_post_xray_waste_percent"] == 12.5
    assert body["calculation_status"] == "estimated"
    assert "does not include rejects" in body["method"]
    assert fake.calls[0]["args"][3] is False


def test_shift_end_xray_count_unavailable_with_reason(monkeypatch):
    fake = recorder(lambda run_id, c, *r: saved_xray(
        run_id, c, waste_status="unavailable",
        post_xray_pack_difference=None, estimated_post_xray_waste_percent=None,
    ))
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_xray_capture", fake)

    response = client.post(
        "/api/v1/runs/5/xray-counts",
        json={"line_technician": "Liam", "production_since_last_update": False,
              "count_unavailable": True, "unavailable_reason": "Counter offline"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["estimated_post_xray_waste_percent"] is None
    assert body["calculation_status"] == "unavailable"
    assert body["waste_unavailable_reason"]


def test_xray_count_below_palletised_output_returns_a_data_quality_warning(monkeypatch):
    warning = "Palletised packs exceed the X-ray pack count."
    fake = recorder(lambda run_id, c, *r: saved_xray(
        run_id, c, waste_status="data_quality_warning", post_xray_pack_difference=Decimal(-75),
        estimated_post_xray_waste_percent=None, warning=warning,
    ))
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_xray_capture", fake)

    response = client.post(
        "/api/v1/runs/5/xray-counts",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 800},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["waste_status"] == "data_quality_warning"
    assert body["post_xray_pack_difference"] == -75.0
    assert body["estimated_post_xray_waste_percent"] is None
    assert body["data_quality_warning"] == warning


@pytest.fixture
def completion_basis(monkeypatch):
    run = {
        "id": 5, "production_line": "Rovema", "status": "Active", "target_speed_ppm": Decimal("8.4"),
        "packs_per_case": 10, "cases_per_pallet": 10, "pack_weight_kg": Decimal("1"),
    }
    monkeypatch.setattr(
        capture, "get_completion_basis",
        lambda run_id: {"run": run, "total_pallets": Decimal("10.5"), "uncovered_pallets": Decimal("8.75")},
    )
    return run


def test_completion_preview_includes_final_production_and_estimated_waste(completion_basis):
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": True,
              "final_pallets_produced": "1.25", "xray_pack_count": 1100},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is False
    assert body["total_pallets_recorded"] == 11.75
    assert body["palletised_pallets"] == 10.0
    assert body["palletised_packs"] == 1000.0
    assert body["post_xray_pack_difference"] == 100.0
    assert body["estimated_post_xray_waste_percent"] == 9.1
    assert body["calculation_status"] == "estimated"


def test_completion_preview_warns_when_values_are_inconsistent(completion_basis):
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 800},
    )

    body = response.json()
    assert body["waste_status"] == "data_quality_warning"
    assert body["estimated_post_xray_waste_percent"] is None
    assert body["post_xray_pack_difference"] == -75.0
    assert body["data_quality_warning"]
    # Both recorded figures stay visible so the operator can see which
    # one needs correcting.
    assert body["xray_pack_count"] == 800
    assert body["palletised_packs"] == 875.0


def test_completion_preview_blocks_completion_when_values_are_inconsistent(completion_basis):
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 800},
    )

    body = response.json()
    assert body["can_complete"] is False
    assert "lower than" in body["blocking_reason"]
    assert "800" in body["blocking_reason"] and "875" in body["blocking_reason"]


@pytest.mark.parametrize("xray_pack_count", [875, 1100])
def test_completion_preview_allows_completion_for_consistent_values(completion_basis, xray_pack_count):
    """Equal counts are zero waste, not a fault; more X-ray packs than
    palletised packs is the normal case."""
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False,
              "xray_pack_count": xray_pack_count},
    )

    body = response.json()
    assert body["can_complete"] is True
    assert body["blocking_reason"] is None
    assert body["post_xray_pack_difference"] >= 0


def test_completion_preview_reports_the_difference_as_xray_minus_palletised(completion_basis):
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 1000},
    )

    body = response.json()
    # 1000 X-ray - 875 palletised = +125, i.e. 12.5% of the X-ray count.
    assert body["post_xray_pack_difference"] == 125.0
    assert body["estimated_post_xray_waste_percent"] == 12.5


def test_completion_preview_without_xray_count_has_no_waste(completion_basis):
    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False,
              "count_unavailable": True, "unavailable_reason": "Counter offline"},
    )

    body = response.json()
    assert body["waste_status"] == "unavailable"
    assert body["estimated_post_xray_waste_percent"] is None
    assert body["palletised_packs"] == 875.0


def test_completion_preview_for_a_completed_run_is_409(completion_basis):
    completion_basis["status"] = "Completed"

    response = client.post(
        "/api/v1/runs/5/completion-preview",
        json={"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 1},
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"line_technician": "Liam", "xray_pack_count": 5},
        {"line_technician": "Liam", "production_since_last_update": False},
        {"line_technician": "Liam", "production_since_last_update": False, "count_unavailable": True},
        {"line_technician": "Liam", "production_since_last_update": False, "count_unavailable": True,
         "unavailable_reason": ""},
        {"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": -5},
        {"line_technician": "Liam", "production_since_last_update": True, "xray_pack_count": 5},
        {"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 5,
         "unavailable_reason": "why"},
    ],
)
def test_xray_count_validation(payload, monkeypatch):
    fake = recorder(saved_xray)
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row())
    monkeypatch.setattr(capture, "record_xray_capture", fake)

    response = client.post("/api/v1/runs/5/xray-counts", json=payload)

    assert response.status_code == 422
    assert fake.calls == []


# ==========================================================
# CHANGEOVERS (paired with their planned stop)
# ==========================================================


def changeover_row(**overrides):
    row = {
        "id": 6, "production_line": "GIC", "line_technician": "Liam", "shift": "Day",
        "status": "Open", "started_at": NOW, "completed_at": None, "completed_by": None,
        "duration_minutes": None, "previous_production_run_id": 5, "planned_downtime_event_id": 3,
        "previous_customer": "Asda", "previous_product": "Basmati",
        "previous_pack_weight_kg": Decimal("1.000"), "previous_format": "Pillow",
        "new_production_run_id": None, "new_customer": "Tesco", "new_product": "Jasmine",
        "new_pack_weight_kg": Decimal("4.000"), "new_format": "Block bottom", "note": None,
    }
    row.update(overrides)
    return row


START_CHANGEOVER = {
    "line_technician": "Liam",
    "new_customer": "Tesco",
    "new_product": "Jasmine",
    "new_pack_weight_kg": "4",
    "new_format": "Block bottom",
}


def test_start_changeover_creates_the_pair_in_one_call(monkeypatch):
    fake = recorder(lambda run_id, tech, new, note, at: {
        "changeover": changeover_row(),
        "planned_downtime": planned_row(reason="Changeover", production_line="GIC"),
    })
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row("GIC"))
    monkeypatch.setattr(capture, "start_run_changeover", fake)

    response = client.post("/api/v1/runs/5/changeovers", json=START_CHANGEOVER)

    assert response.status_code == 201
    body = response.json()
    assert body["changeover"]["previous_customer"] == "Asda"
    assert body["changeover"]["new_customer"] == "Tesco"
    assert body["changeover"]["new_pack_weight_kg"] == 4.0
    assert body["planned_downtime"]["reason"] == "Changeover"
    args = fake.calls[0]["args"]
    assert args[2] == {"new_customer": "Tesco", "new_product": "Jasmine",
                       "new_pack_weight_kg": Decimal("4"), "new_format": "Block bottom"}
    assert fake.calls[0]["idempotency"].action == "changeover_start:5"


@pytest.mark.parametrize(
    "overrides",
    [
        {"new_customer": "  "},
        {"new_product": ""},
        {"new_format": " "},
        {"new_pack_weight_kg": "0"},
        {"new_pack_weight_kg": "-1"},
        {"line_technician": "Nobody"},
    ],
)
def test_start_changeover_requires_the_new_configuration(overrides, monkeypatch):
    fake = recorder(lambda *a: {})
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row("GIC"))
    monkeypatch.setattr(capture, "start_run_changeover", fake)

    response = client.post("/api/v1/runs/5/changeovers", json={**START_CHANGEOVER, **overrides})

    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    "message",
    ["Production Line 'GIC' already has an open changeover.", "Planned downtime is already in progress for this run."],
)
def test_start_changeover_conflicts_are_409(message, monkeypatch):
    monkeypatch.setattr(capture, "get_production_run_by_id", run_row("GIC"))
    monkeypatch.setattr(capture, "start_run_changeover", raising(PulseCaptureError(409, message)))

    response = client.post("/api/v1/runs/5/changeovers", json=START_CHANGEOVER)

    assert response.status_code == 409
    assert response.json()["detail"] == message


def test_complete_changeover_requires_first_acceptable_packs_confirmation(monkeypatch):
    fake = recorder(lambda *a: {})
    monkeypatch.setattr(capture, "complete_run_changeover", fake)

    missing = client.post("/api/v1/changeovers/6/complete", json={"completed_by": "Liam"})
    declined = client.post(
        "/api/v1/changeovers/6/complete", json={"completed_by": "Liam", "first_acceptable_packs_confirmed": False}
    )

    assert missing.status_code == declined.status_code == 422
    assert fake.calls == []


def test_complete_changeover_ends_the_pair(monkeypatch):
    fake = recorder(lambda changeover_id, by, note, at: {
        "changeover": changeover_row(status="Completed", completed_at=NOW, completed_by="Liam",
                                     duration_minutes=Decimal("42.5000")),
        "planned_downtime": planned_row(reason="Changeover", ended_at=NOW, ended_by="Liam",
                                        duration_minutes=Decimal("42.5000")),
    })
    monkeypatch.setattr(capture, "complete_run_changeover", fake)

    response = client.post(
        "/api/v1/changeovers/6/complete", json={"completed_by": "Liam", "first_acceptable_packs_confirmed": True}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["changeover"]["status"] == "Completed"
    assert body["changeover"]["duration_minutes"] == 42.5
    assert body["planned_downtime"]["duration_minutes"] == 42.5
    assert fake.calls[0]["idempotency"].action == "changeover_complete:6"


def test_double_completed_changeover_replays(monkeypatch):
    original = {"status": "success", "changeover": {"changeover_id": 6, "status": "Completed"}}
    monkeypatch.setattr(capture, "complete_run_changeover", raising(IdempotentReplay(200, original)))

    response = client.post(
        "/api/v1/changeovers/6/complete", json={"completed_by": "Liam", "first_acceptable_packs_confirmed": True}
    )

    assert response.status_code == 200
    assert response.json() == original


@pytest.mark.parametrize("error, status", [
    (PulseCaptureError(409, "Changeover 6 is already completed."), 409),
    (PulseCaptureError(404, "Changeover 6 was not found."), 404),
    (RuntimeError(SECRET), 503),
])
def test_complete_changeover_failures_are_safe(error, status, monkeypatch):
    monkeypatch.setattr(capture, "complete_run_changeover", raising(error))

    response = client.post(
        "/api/v1/changeovers/6/complete", json={"completed_by": "Liam", "first_acceptable_packs_confirmed": True}
    )

    assert response.status_code == status
    assert "s3cr3t" not in response.text


def test_open_changeover_lookup(monkeypatch):
    monkeypatch.setattr(capture, "get_open_changeover", lambda line: changeover_row() if line == "GIC" else None)

    assert client.get("/api/v1/changeovers/open", params={"production_line": "GIC"}).json()[
        "open_changeover"]["changeover_id"] == 6
    assert client.get("/api/v1/changeovers/open", params={"production_line": "Rovema"}).json() == {
        "open_changeover": None}
    assert client.get("/api/v1/changeovers/open", params={"production_line": "Nowhere"}).status_code == 422


# ==========================================================
# ACTIVE-RUN RECOVERY
# ==========================================================


def hmi_state(**overrides):
    state = {
        "run": {
            "id": 5, "production_line": "Rovema", "line_technician": "Liam", "shift": "Days",
            "customer": "Asda", "product": "White Basmati", "format": "Pillow", "pack_type": "1 kg x 10",
            "pack_weight_kg": Decimal("1.000"), "packs_per_case": 10, "cases_per_pallet": 10,
            "target_speed_ppm": Decimal("8.4"), "status": "Active",
            "started_at": datetime(2026, 1, 12, 6, 5, tzinfo=timezone.utc), "finished_at": None,
            "starting_pallets_remaining": 25, "pallets_remaining": Decimal("21.25"),
            "total_pallets_completed": Decimal("3.75"), "potential_overrun_pallets": Decimal(0),
        },
        "hourly": {
            "hourly_update_count": 1, "pallets_recorded": Decimal("3.75"), "expected_packs": Decimal("504"),
            "last_period_ended_at": datetime(2026, 1, 12, 7, 5, tzinfo=timezone.utc),
        },
        "planned": [
            planned_row(started_at=datetime(2026, 1, 12, 6, 30, tzinfo=timezone.utc),
                        ended_at=datetime(2026, 1, 12, 6, 40, tzinfo=timezone.utc),
                        duration_minutes=Decimal(10)),
            planned_row(id=4, reason="CCP Check", started_at=datetime(2026, 1, 12, 7, 50, tzinfo=timezone.utc)),
        ],
        "open_changeover": None,
        "faults": [{"opened_at": datetime(2026, 1, 12, 7, 0, tzinfo=timezone.utc),
                    "resolved_at": datetime(2026, 1, 12, 7, 15, tzinfo=timezone.utc),
                    "production_status": "Resolved"}],
    }
    state.update(overrides)
    return state


def test_hmi_state_restores_saved_totals_and_open_planned_downtime(monkeypatch):
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: hmi_state())

    response = client.get("/api/v1/runs/5/hmi-state")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["status"] == "Active"
    assert body["run"]["pallets_remaining"] == 21.25
    assert body["progress"]["pallets_recorded"] == 3.75
    assert body["progress"]["actual_packs"] == 375.0
    assert body["progress"]["output_gap_packs"] == 129.0
    assert body["progress"]["production_achievement_percent"] == 74.4
    # 10 min completed + 10 min open (07:50 -> 08:00)
    assert body["progress"]["planned_downtime_minutes"] == 20.0
    assert body["progress"]["unplanned_downtime_minutes"] == 15.0
    assert body["progress"]["next_hourly_update_due_at"] == "2026-01-12T08:10:00+00:00"
    assert body["open_planned_downtime"]["reason"] == "CCP Check"
    assert body["open_changeover"] is None


def test_hmi_state_restores_an_open_changeover(monkeypatch):
    monkeypatch.setattr(
        capture, "get_hmi_run_state",
        lambda run_id: hmi_state(
            planned=[planned_row(reason="Changeover")], open_changeover=changeover_row()
        ),
    )

    body = client.get("/api/v1/runs/5/hmi-state").json()

    assert body["open_changeover"]["changeover_id"] == 6
    assert body["open_changeover"]["new_customer"] == "Tesco"
    assert body["open_planned_downtime"]["reason"] == "Changeover"


# ----------------------------------------------------------
# Active downtime duration
# ----------------------------------------------------------


def test_active_planned_downtime_is_split_from_completed_downtime(monkeypatch):
    """A stop in progress must not read as zero just because it is open.
    10 min completed (06:30-06:40) + 10 min active (07:50 -> now 08:00)."""
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: hmi_state())

    progress = client.get("/api/v1/runs/5/hmi-state").json()["progress"]

    assert progress["planned_downtime_completed_minutes"] == 10.0
    assert progress["planned_downtime_active_minutes"] == 10.0
    assert progress["planned_downtime_minutes"] == 20.0


def test_an_open_stop_reports_its_elapsed_time_not_a_null_duration(monkeypatch):
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: hmi_state())

    open_stop = client.get("/api/v1/runs/5/hmi-state").json()["open_planned_downtime"]

    assert open_stop["is_active"] is True
    # duration_minutes stays null until the stop is actually ended...
    assert open_stop["duration_minutes"] is None
    # ...but the elapsed time is reported from the server clock.
    assert open_stop["elapsed_minutes"] == 10.0


def test_completed_only_downtime_reports_no_active_minutes(monkeypatch):
    monkeypatch.setattr(
        capture, "get_hmi_run_state",
        lambda run_id: hmi_state(planned=[
            planned_row(started_at=datetime(2026, 1, 12, 6, 30, tzinfo=timezone.utc),
                        ended_at=datetime(2026, 1, 12, 6, 45, tzinfo=timezone.utc),
                        duration_minutes=Decimal(15)),
        ]),
    )

    body = client.get("/api/v1/runs/5/hmi-state").json()

    assert body["progress"]["planned_downtime_completed_minutes"] == 15.0
    assert body["progress"]["planned_downtime_active_minutes"] is None
    assert body["progress"]["planned_downtime_minutes"] == 15.0
    assert body["open_planned_downtime"] is None


def test_active_only_downtime_reports_no_completed_minutes(monkeypatch):
    monkeypatch.setattr(
        capture, "get_hmi_run_state",
        lambda run_id: hmi_state(planned=[
            planned_row(started_at=datetime(2026, 1, 12, 7, 49, tzinfo=timezone.utc)),
        ]),
    )

    progress = client.get("/api/v1/runs/5/hmi-state").json()["progress"]

    assert progress["planned_downtime_completed_minutes"] == 0.0
    assert progress["planned_downtime_active_minutes"] == 11.0
    assert progress["planned_downtime_minutes"] == 11.0


def test_no_planned_downtime_at_all_is_zero_and_not_active(monkeypatch):
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: hmi_state(planned=[]))

    progress = client.get("/api/v1/runs/5/hmi-state").json()["progress"]

    assert progress["planned_downtime_completed_minutes"] == 0.0
    assert progress["planned_downtime_active_minutes"] is None
    assert progress["planned_downtime_minutes"] == 0.0


def test_the_total_never_counts_the_same_minutes_twice(monkeypatch):
    """Overlapping stops are merged, so completed + active can exceed the
    total - the merged total stays the authority."""
    monkeypatch.setattr(
        capture, "get_hmi_run_state",
        lambda run_id: hmi_state(planned=[
            planned_row(started_at=datetime(2026, 1, 12, 7, 40, tzinfo=timezone.utc),
                        ended_at=datetime(2026, 1, 12, 7, 55, tzinfo=timezone.utc),
                        duration_minutes=Decimal(15)),
            planned_row(id=4, started_at=datetime(2026, 1, 12, 7, 50, tzinfo=timezone.utc)),
        ]),
    )

    progress = client.get("/api/v1/runs/5/hmi-state").json()["progress"]

    # 07:40 -> 08:00 merged = 20 minutes, not 15 + 10.
    assert progress["planned_downtime_minutes"] == 20.0
    assert progress["planned_downtime_completed_minutes"] == 15.0
    assert progress["planned_downtime_active_minutes"] == 10.0


def test_a_changeover_owned_stop_reports_both_active_durations(monkeypatch):
    monkeypatch.setattr(
        capture, "get_hmi_run_state",
        lambda run_id: hmi_state(
            planned=[planned_row(reason="Changeover",
                                 started_at=datetime(2026, 1, 12, 7, 45, tzinfo=timezone.utc))],
            open_changeover=changeover_row(),
        ),
    )

    body = client.get("/api/v1/runs/5/hmi-state").json()

    assert body["progress"]["planned_downtime_active_minutes"] == 15.0
    assert body["progress"]["changeover_active_minutes"] is not None
    assert body["open_planned_downtime"]["is_active"] is True
    assert body["open_planned_downtime"]["elapsed_minutes"] == 15.0


def test_a_later_refresh_reports_a_larger_active_duration(monkeypatch):
    """The backend stays authoritative: each read recomputes elapsed from
    the server clock, so a tablet's own timer is corrected on refresh."""
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: hmi_state())

    first = client.get("/api/v1/runs/5/hmi-state").json()

    monkeypatch.setattr(capture, "_now", lambda: NOW + timedelta(minutes=7))
    second = client.get("/api/v1/runs/5/hmi-state").json()

    assert first["progress"]["planned_downtime_active_minutes"] == 10.0
    assert second["progress"]["planned_downtime_active_minutes"] == 17.0
    assert second["generated_at"] > first["generated_at"]
    # Completed downtime is unaffected by the passage of time.
    assert second["progress"]["planned_downtime_completed_minutes"] == 10.0


def test_hmi_state_first_prompt_follows_run_start(monkeypatch):
    state = hmi_state()
    state["hourly"] = {"hourly_update_count": 0, "pallets_recorded": Decimal(0),
                       "expected_packs": Decimal(0), "last_period_ended_at": None}
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: state)

    body = client.get("/api/v1/runs/5/hmi-state").json()

    assert body["progress"]["next_hourly_update_due_at"] == "2026-01-12T07:10:00+00:00"
    assert body["progress"]["production_achievement_percent"] is None


def test_hmi_state_unknown_run_is_404_and_failure_is_safe_503(monkeypatch):
    monkeypatch.setattr(capture, "get_hmi_run_state", lambda run_id: None)
    assert client.get("/api/v1/runs/404/hmi-state").status_code == 404

    monkeypatch.setattr(capture, "get_hmi_run_state", raising(RuntimeError(SECRET)))
    response = client.get("/api/v1/runs/5/hmi-state")
    assert response.status_code == 503
    assert "s3cr3t" not in response.text


def test_all_capture_routes_are_registered():
    paths = app.openapi()["paths"]
    for path, method in [
        ("/api/v1/runs/{run_id}/hourly-updates", "post"),
        ("/api/v1/runs/{run_id}/planned-downtime", "post"),
        ("/api/v1/planned-downtime/{planned_downtime_id}/end", "post"),
        ("/api/v1/runs/{run_id}/faults", "post"),
        ("/api/v1/runs/{run_id}/xray-counts", "post"),
        ("/api/v1/runs/{run_id}/completion-preview", "post"),
        ("/api/v1/runs/{run_id}/changeovers", "post"),
        ("/api/v1/changeovers/{changeover_id}/complete", "post"),
        ("/api/v1/changeovers/open", "get"),
        ("/api/v1/runs/{run_id}/hmi-state", "get"),
    ]:
        assert method in paths[path], f"missing {method.upper()} {path}"
    assert "/api/v1/changeovers" not in paths
