"""
Offline tests for the HMI-facing Production Run API in src/runs_api.py,
composed onto the main app in src/api.py.

These tests never touch Supabase: every src.database function
src/runs_api.py uses (create_production_run, record_xray_capture) and
the run lookup it shares with src/pulse_capture_api.py are monkeypatched
at the point where each module imported them.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import pulse_capture_api, runs_api
from src.api import HMI_ORIGIN, app
from src.database import IdempotentReplay, PulseCaptureError


IDEMPOTENCY_KEY = "run-test-key-0000000000000001"

client = TestClient(app, headers={"Idempotency-Key": IDEMPOTENCY_KEY})

VALID_PAYLOAD = {
    "production_line": "Rovema",
    "line_technician": "Liam",
    "shift": "Night",
    "customer": "Asda",
    "product": "Basmati",
    "pack_weight": "1kg",
    "pack_weight_kg": 1.0,
    "packs_per_case": 8,
    "pack_type": "Pillow",
    "target_speed_ppm": 120,
    "cases_per_pallet": 220,
    "pallets_remaining": 38,
    "previous_run_completed": 0,
}


def fake_create(run_id=123, captured=None):
    def create(run, idempotency=None):
        if captured is not None:
            captured.update(run=run, idempotency=idempotency)
        return {**run, "run_id": run_id}

    return create


# ==========================================================
# SUCCESSFUL RUN START
# ==========================================================


def test_start_run_success(monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create(123))

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json() == {
        "status": "success",
        "message": "Run started",
        "run_id": 123,
        "production_line": "Rovema",
        "line_technician": "Liam",
        "pallets_remaining": 38,
    }


def test_start_run_passes_expected_shape_and_idempotency(monkeypatch):
    captured = {}
    monkeypatch.setattr(runs_api, "create_production_run", fake_create(7, captured))

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert captured["run"] == {
        "production_line": "Rovema",
        "line_technician": "Liam",
        "shift": "Night",
        "customer": "Asda",
        "product": "Basmati",
        "pack_weight_kg": 1.0,
        "packs_per_case": 8,
        "pack_type": "Pillow",
        "target_speed_ppm": 120,
        "cases_per_pallet": 220,
        "starting_pallets_remaining": 38,
        "pallets_remaining": 38,
        "previous_run_completed": 0,
        "format": None,
    }
    assert captured["idempotency"].key == IDEMPOTENCY_KEY
    assert captured["idempotency"].action == "run_start:Rovema"


def test_start_run_passes_optional_format_when_sent(monkeypatch):
    captured = {}
    monkeypatch.setattr(runs_api, "create_production_run", fake_create(8, captured))

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, "format": "  Pillow 8x1kg  "})

    assert response.status_code == 201
    assert captured["run"]["format"] == "Pillow 8x1kg"


# ==========================================================
# IDEMPOTENCY
# ==========================================================


@pytest.mark.parametrize("key", [None, "short", "has spaces in the key!!", "x" * 101])
def test_start_run_requires_a_valid_idempotency_key(key, monkeypatch):
    calls = []
    monkeypatch.setattr(runs_api, "create_production_run", lambda *a, **k: calls.append(a))
    anonymous = TestClient(app)

    headers = {} if key is None else {"Idempotency-Key": key}
    response = anonymous.post("/api/v1/runs", json=VALID_PAYLOAD, headers=headers)

    assert response.status_code == 422
    assert calls == []


def test_retried_start_run_replays_the_original_response(monkeypatch):
    stored = {"status": "success", "message": "Run started", "run_id": 123,
              "production_line": "Rovema", "line_technician": "Liam", "pallets_remaining": 38}

    def replay(run, idempotency=None):
        raise IdempotentReplay(201, stored)

    monkeypatch.setattr(runs_api, "create_production_run", replay)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json() == stored
    assert response.headers["idempotent-replayed"] == "true"


def test_same_key_with_different_run_details_is_409(monkeypatch):
    def reused(run, idempotency=None):
        raise PulseCaptureError(409, "This request was already used with different details.")

    monkeypatch.setattr(runs_api, "create_production_run", reused)

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, "customer": "Tesco"})

    assert response.status_code == 409


def test_fingerprint_changes_with_the_request_details(monkeypatch):
    fingerprints = []
    monkeypatch.setattr(
        runs_api,
        "create_production_run",
        lambda run, idempotency=None: fingerprints.append(idempotency.fingerprint) or {**run, "run_id": 1},
    )

    client.post("/api/v1/runs", json=VALID_PAYLOAD)
    client.post("/api/v1/runs", json=VALID_PAYLOAD)
    client.post("/api/v1/runs", json={**VALID_PAYLOAD, "customer": "Tesco"})

    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[0] != fingerprints[2]


# ==========================================================
# VALIDATION
# ==========================================================


@pytest.mark.parametrize("field", ["shift", "customer", "product", "pack_type"])
def test_start_run_rejects_blank_required_text(field, monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create())

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, field: "   "})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("pack_weight_kg", 0),
        ("pack_weight_kg", -1.5),
        ("packs_per_case", 0),
        ("target_speed_ppm", 0),
        ("cases_per_pallet", 0),
        ("pallets_remaining", -1),
        ("previous_run_completed", -1),
    ],
)
def test_start_run_rejects_invalid_values(field, value, monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create())

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, field: value})

    assert response.status_code == 422


def test_start_run_rejects_unknown_production_line(monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create())

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, "production_line": "NotARealLine"})

    assert response.status_code == 422


def test_start_run_rejects_unknown_line_technician_name(monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create())

    response = client.post("/api/v1/runs", json={**VALID_PAYLOAD, "line_technician": "NotARealTechnician"})

    assert response.status_code == 422


REQUIRED_TECHNICIANS = [
    "Marina", "Mariusz", "Liam", "Ben", "Tomasz", "Sumit",
    "Gurpreet", "Baljeet", "Pali", "Diego", "Seb", "Bupreet",
]


@pytest.mark.parametrize("production_line", ["Rovema", "GIC", "Guill"])
@pytest.mark.parametrize("line_technician", REQUIRED_TECHNICIANS)
def test_start_run_accepts_every_required_technician_on_every_line(
    production_line, line_technician, monkeypatch
):
    # There are no confirmed line-specific technician assignments:
    # every required technician must be accepted on every line.
    monkeypatch.setattr(runs_api, "create_production_run", fake_create(55))

    response = client.post(
        "/api/v1/runs",
        json={**VALID_PAYLOAD, "production_line": production_line, "line_technician": line_technician},
    )

    assert response.status_code == 201
    assert response.json()["line_technician"] == line_technician


def test_start_run_rejects_duplicate_active_run(monkeypatch):
    def active(run, idempotency=None):
        raise PulseCaptureError(409, "Production Line 'Rovema' already has an active Production Run.")

    monkeypatch.setattr(runs_api, "create_production_run", active)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 409
    assert "already has an active Production Run" in response.json()["detail"]


# ==========================================================
# DATABASE FAILURE
# ==========================================================


SENSITIVE_ERROR_TEXT = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


def _assert_no_sensitive_text_anywhere(response, captured):
    for text in (response.text, captured.out, captured.err):
        assert "s3cr3t-p4ssw0rd" not in text
        assert "postgresql://" not in text


def test_start_run_returns_safe_error_when_save_fails(monkeypatch, capsys):
    def broken(run, idempotency=None):
        raise RuntimeError(SENSITIVE_ERROR_TEXT)

    monkeypatch.setattr(runs_api, "create_production_run", broken)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 503
    _assert_no_sensitive_text_anywhere(response, capsys.readouterr())


# ==========================================================
# CORS
# ==========================================================


def test_cors_allows_configured_hmi_origin(monkeypatch):
    monkeypatch.setattr(runs_api, "create_production_run", fake_create(1))

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD, headers={"Origin": HMI_ORIGIN})

    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == HMI_ORIGIN


def test_cors_preflight_allows_the_idempotency_key_header():
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": HMI_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == HMI_ORIGIN
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_other_origins():
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "https://some-other-site.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert "access-control-allow-origin" not in response.headers


# ==========================================================
# COMPLETE RUN
# ==========================================================
# Completing a run requires: whether production was made since the last
# hourly update (and if so the final pallets), plus the X-ray pack count
# or "count unavailable" with a reason. record_xray_capture writes the
# final hourly update, the X-ray row and the run closure in ONE
# transaction.

NOW = datetime(2026, 1, 12, 13, 55, tzinfo=timezone.utc)

COMPLETE_WITH_COUNT = {
    "line_technician": "Liam",
    "production_since_last_update": False,
    "xray_pack_count": 9000,
}
COMPLETE_WITH_FINAL_PRODUCTION = {
    "line_technician": "Liam",
    "production_since_last_update": True,
    "final_pallets_produced": "1.25",
    "xray_pack_count": 9000,
}
COMPLETE_UNAVAILABLE = {
    "line_technician": "Liam",
    "production_since_last_update": False,
    "count_unavailable": True,
    "unavailable_reason": "X-ray counter was reset mid-shift",
}


def _saved_capture(run_id, capture, **overrides):
    saved = {
        "xray_capture_id": 5,
        "captured_at": NOW,
        "capture_point": "run_completion",
        "production_run_id": run_id,
        "production_line": "GIC",
        "shift": "Day",
        "count_available": capture["count_available"],
        "xray_pack_count": capture["xray_pack_count"],
        "unavailable_reason": capture["unavailable_reason"],
        "final_hourly_update": None,
        "total_pallets_recorded": Decimal("11.25"),
        "palletised_pallets": Decimal("11.25"),
        "palletised_packs": Decimal("9000"),
        "pallets_remaining": Decimal("0"),
        "total_pallets_completed": Decimal("11.25"),
        "potential_overrun_pallets": Decimal("0"),
        "waste_status": "estimated",
        "post_xray_pack_difference": Decimal("0"),
        "estimated_post_xray_waste_percent": Decimal("0"),
        "warning": None,
    }
    saved.update(overrides)
    return saved


@pytest.fixture
def gic_run(monkeypatch):
    monkeypatch.setattr(
        pulse_capture_api,
        "get_production_run_by_id",
        lambda run_id: {"id": run_id, "production_line": "GIC", "status": "Active"},
    )


def test_complete_run_with_no_final_production(monkeypatch, gic_run):
    calls = []

    def fake_capture(run_id, capture, captured_at, complete_run, idempotency=None):
        calls.append((run_id, capture, complete_run, idempotency.action))
        return _saved_capture(run_id, capture)

    monkeypatch.setattr(runs_api, "record_xray_capture", fake_capture)

    response = client.post("/api/v1/runs/24/complete", json=COMPLETE_WITH_COUNT)

    assert response.status_code == 200
    body = response.json()
    assert body["run_status"] == "Completed"
    assert body["xray"]["xray_pack_count"] == 9000
    assert body["xray"]["final_pallets_produced"] is None
    assert calls == [(24, {
        "line_technician": "Liam",
        "final_pallets_produced": None,
        "count_available": True,
        "xray_pack_count": 9000,
        "unavailable_reason": None,
    }, True, "run_complete:24")]


def test_complete_run_saves_decimal_final_production_in_the_same_call(monkeypatch, gic_run):
    received = {}

    def fake_capture(run_id, capture, captured_at, complete_run, idempotency=None):
        received.update(capture)
        return _saved_capture(
            run_id, capture,
            final_hourly_update={"hourly_update_id": 88, "actual_pallets": Decimal("1.2500")},
            total_pallets_recorded=Decimal("12.5"),
        )

    monkeypatch.setattr(runs_api, "record_xray_capture", fake_capture)

    response = client.post("/api/v1/runs/24/complete", json=COMPLETE_WITH_FINAL_PRODUCTION)

    assert response.status_code == 200
    assert received["final_pallets_produced"] == Decimal("1.25")
    xray = response.json()["xray"]
    assert xray["final_hourly_update_id"] == 88
    assert xray["final_pallets_produced"] == 1.25
    assert xray["total_pallets_recorded"] == 12.5


def test_complete_run_with_count_unavailable_and_reason(monkeypatch, gic_run):
    monkeypatch.setattr(
        runs_api,
        "record_xray_capture",
        lambda run_id, capture, at, complete, idempotency=None: _saved_capture(
            run_id, capture, waste_status="unavailable",
            post_xray_pack_difference=None, estimated_post_xray_waste_percent=None,
        ),
    )

    response = client.post("/api/v1/runs/24/complete", json=COMPLETE_UNAVAILABLE)

    assert response.status_code == 200
    xray = response.json()["xray"]
    assert xray["count_available"] is False
    assert xray["estimated_post_xray_waste_percent"] is None
    assert xray["calculation_status"] == "unavailable"


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"line_technician": "Liam", "xray_pack_count": 10},
        {"line_technician": "Liam", "production_since_last_update": False},
        {"line_technician": "Liam", "production_since_last_update": False, "count_unavailable": True},
        {"line_technician": "Liam", "production_since_last_update": False, "count_unavailable": True,
         "unavailable_reason": "   "},
        {"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": -1},
        {"line_technician": "Liam", "production_since_last_update": True, "xray_pack_count": 10},
        {"line_technician": "Liam", "production_since_last_update": True, "final_pallets_produced": "0",
         "xray_pack_count": 10},
        {"line_technician": "Liam", "production_since_last_update": True, "final_pallets_produced": "-1",
         "xray_pack_count": 10},
        {"line_technician": "Liam", "production_since_last_update": False, "final_pallets_produced": "2",
         "xray_pack_count": 10},
        {"line_technician": "Liam", "production_since_last_update": False, "xray_pack_count": 10,
         "count_unavailable": True, "unavailable_reason": "Counter broken"},
    ],
)
def test_complete_run_validation_rejects_before_any_write(body, monkeypatch, gic_run):
    called = []
    monkeypatch.setattr(runs_api, "record_xray_capture", lambda *a, **k: called.append(a))

    response = client.post("/api/v1/runs/24/complete", json=body)

    assert response.status_code == 422
    assert called == []


def test_complete_run_rejects_unknown_technician(monkeypatch, gic_run):
    called = []
    monkeypatch.setattr(runs_api, "record_xray_capture", lambda *a, **k: called.append(a))

    response = client.post(
        "/api/v1/runs/24/complete", json={**COMPLETE_WITH_COUNT, "line_technician": "Nobody"}
    )

    assert response.status_code == 422
    assert called == []


def test_complete_run_returns_404_for_unknown_run(monkeypatch):
    called = []
    monkeypatch.setattr(pulse_capture_api, "get_production_run_by_id", lambda run_id: None)
    monkeypatch.setattr(runs_api, "record_xray_capture", lambda *a, **k: called.append(a))

    response = client.post("/api/v1/runs/999999/complete", json=COMPLETE_WITH_COUNT)

    assert response.status_code == 404
    assert called == []


def test_complete_run_already_completed_is_409_from_the_transaction(monkeypatch, gic_run):
    def already(*args, **kwargs):
        raise PulseCaptureError(409, "Production Run 10 is not active.")

    monkeypatch.setattr(runs_api, "record_xray_capture", already)

    response = client.post("/api/v1/runs/10/complete", json=COMPLETE_WITH_COUNT)

    assert response.status_code == 409


def test_double_submitted_complete_run_replays_instead_of_409(monkeypatch):
    # The first request completed the run; the retry (same key, same body)
    # must still get the original success, not "already completed".
    stored = {"status": "success", "message": "Run completed", "run_id": 10,
              "production_line": "GIC", "run_status": "Completed", "xray": {"xray_capture_id": 5}}
    monkeypatch.setattr(
        pulse_capture_api,
        "get_production_run_by_id",
        lambda run_id: {"id": run_id, "production_line": "GIC", "status": "Completed"},
    )

    def replay(*args, **kwargs):
        raise IdempotentReplay(200, stored)

    monkeypatch.setattr(runs_api, "record_xray_capture", replay)

    response = client.post("/api/v1/runs/10/complete", json=COMPLETE_WITH_COUNT)

    assert response.status_code == 200
    assert response.json() == stored
    assert response.headers["idempotent-replayed"] == "true"


def test_complete_run_transaction_failure_is_safe_503(monkeypatch, capsys, gic_run):
    def broken(*args, **kwargs):
        raise RuntimeError(SENSITIVE_ERROR_TEXT)

    monkeypatch.setattr(runs_api, "record_xray_capture", broken)

    response = client.post("/api/v1/runs/12/complete", json=COMPLETE_WITH_COUNT)

    assert response.status_code == 503
    _assert_no_sensitive_text_anywhere(response, capsys.readouterr())


# ==========================================================
# EXISTING WHATSAPP ROUTES STILL WORK (THROUGH THE COMPOSED APP)
# ==========================================================


def test_whatsapp_health_route_still_works_through_composed_app():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_whatsapp_webhook_post_still_works_through_composed_app():
    response = client.post(
        "/webhooks/whatsapp",
        json={"object": "whatsapp_business_account", "entry": []},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "received"
