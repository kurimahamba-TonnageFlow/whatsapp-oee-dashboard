"""
Offline tests for the HMI-facing Production Run API in src/runs_api.py,
composed onto the main app in src/api.py.

These tests never touch Supabase: src.database.get_active_production_run
and src.database.save_production_run are monkeypatched at the point where
src/runs_api.py imported them.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import runs_api
from src.api import HMI_ORIGIN, app


client = TestClient(app)

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


@pytest.fixture(autouse=True)
def reset_duplicate_submission_locks():
    # Each test starts with a clean per-line lock table so one test's
    # lock acquisition can never leak into another test.
    runs_api._line_locks.clear()
    yield


# ==========================================================
# SUCCESSFUL RUN START
# ==========================================================


def test_start_run_success(monkeypatch):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 123)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 201

    body = response.json()
    assert body == {
        "status": "success",
        "message": "Run started",
        "run_id": 123,
        "production_line": "Rovema",
        "line_technician": "Liam",
        "pallets_remaining": 38,
    }


def test_start_run_passes_expected_shape_to_save_production_run(monkeypatch):
    captured = {}

    def fake_save(run):
        captured.update(run)
        return 7

    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", fake_save)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert captured == {
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
    }


# ==========================================================
# BLANK REQUIRED FIELDS
# ==========================================================


@pytest.mark.parametrize(
    "field",
    ["shift", "customer", "product", "pack_type"],
)
def test_start_run_rejects_blank_required_text(field, monkeypatch):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    payload = {**VALID_PAYLOAD, field: "   "}

    response = client.post("/api/v1/runs", json=payload)

    assert response.status_code == 422


# ==========================================================
# INVALID VALUES
# ==========================================================


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
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    payload = {**VALID_PAYLOAD, field: value}

    response = client.post("/api/v1/runs", json=payload)

    assert response.status_code == 422


def test_start_run_rejects_unknown_production_line(monkeypatch):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    payload = {**VALID_PAYLOAD, "production_line": "NotARealLine"}

    response = client.post("/api/v1/runs", json=payload)

    assert response.status_code == 422


def test_start_run_rejects_unknown_line_technician_name(monkeypatch):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    payload = {**VALID_PAYLOAD, "line_technician": "NotARealTechnician"}

    response = client.post("/api/v1/runs", json=payload)

    assert response.status_code == 422


REQUIRED_TECHNICIANS = [
    "Marina",
    "Mariusz",
    "Liam",
    "Ben",
    "Tomasz",
    "Sumit",
    "Gurpreet",
    "Baljeet",
    "Pali",
    "Diego",
    "Seb",
    "Bupreet",
]


@pytest.mark.parametrize("production_line", ["Rovema", "GIC", "Guill"])
@pytest.mark.parametrize("line_technician", REQUIRED_TECHNICIANS)
def test_start_run_accepts_every_required_technician_on_every_line(
    production_line, line_technician, monkeypatch
):
    # There are no confirmed line-specific technician assignments:
    # every required technician must be accepted on every line.
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 55)

    payload = {
        **VALID_PAYLOAD,
        "production_line": production_line,
        "line_technician": line_technician,
    }

    response = client.post("/api/v1/runs", json=payload)

    assert response.status_code == 201
    assert response.json()["line_technician"] == line_technician


# ==========================================================
# DUPLICATE ACTIVE RUN
# ==========================================================


def test_start_run_rejects_duplicate_active_run(monkeypatch):
    monkeypatch.setattr(
        runs_api,
        "get_active_production_run",
        lambda line: {"id": 1, "production_line": line},
    )
    save_called = {"count": 0}

    def fake_save(run):
        save_called["count"] += 1
        return 99

    monkeypatch.setattr(runs_api, "save_production_run", fake_save)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 409
    assert save_called["count"] == 0

    body = response.json()
    assert "already has an active Production Run" in body["detail"]


# ==========================================================
# DATABASE FAILURE
# ==========================================================


SENSITIVE_ERROR_TEXT = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


def _assert_no_sensitive_text_anywhere(response, captured):
    body_text = response.text

    assert "s3cr3t-p4ssw0rd" not in body_text
    assert "postgresql://" not in body_text

    assert "s3cr3t-p4ssw0rd" not in captured.out
    assert "postgresql://" not in captured.out

    assert "s3cr3t-p4ssw0rd" not in captured.err
    assert "postgresql://" not in captured.err


def test_start_run_returns_safe_error_when_active_run_check_fails(monkeypatch, capsys):
    def fake_get_active(line):
        raise RuntimeError(SENSITIVE_ERROR_TEXT)

    monkeypatch.setattr(runs_api, "get_active_production_run", fake_get_active)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 503

    body = response.json()
    assert "secret" not in body["detail"]
    assert "postgresql://" not in body["detail"]

    _assert_no_sensitive_text_anywhere(response, capsys.readouterr())


def test_start_run_returns_safe_error_when_save_fails(monkeypatch, capsys):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)

    def fake_save(run):
        raise RuntimeError(SENSITIVE_ERROR_TEXT)

    monkeypatch.setattr(runs_api, "save_production_run", fake_save)

    response = client.post("/api/v1/runs", json=VALID_PAYLOAD)

    assert response.status_code == 503

    body = response.json()
    assert "secret" not in body["detail"]
    assert "postgresql://" not in body["detail"]

    _assert_no_sensitive_text_anywhere(response, capsys.readouterr())


# ==========================================================
# CORS
# ==========================================================


def test_cors_allows_configured_hmi_origin(monkeypatch):
    monkeypatch.setattr(runs_api, "get_active_production_run", lambda line: None)
    monkeypatch.setattr(runs_api, "save_production_run", lambda run: 1)

    response = client.post(
        "/api/v1/runs",
        json=VALID_PAYLOAD,
        headers={"Origin": HMI_ORIGIN},
    )

    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == HMI_ORIGIN


def test_cors_preflight_allows_configured_hmi_origin():
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": HMI_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == HMI_ORIGIN


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
