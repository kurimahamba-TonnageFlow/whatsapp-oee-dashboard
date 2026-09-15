"""
Offline tests for the Management API (src/management_api.py) and the
public HMI config endpoint (src/hmi_config_api.py), composed onto the
app in src/api.py.

Never touches Supabase: every src.database function these modules
imported is monkeypatched at the point where they imported it.
"""

from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import database, hmi_config_api, management_api, management_auth
from src.api import DASHBOARD_ORIGIN, HMI_ORIGIN, app


client = TestClient(app)

TEST_PIN = "test-pin-0000"


@pytest.fixture(autouse=True)
def reset_management_state(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", TEST_PIN)
    management_auth._sessions.clear()
    management_auth._login_attempts.clear()
    yield


def _login(manager_name="Kuri"):
    response = client.post(
        "/api/v1/management/login",
        json={"pin": TEST_PIN, "manager_name": manager_name},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================


def test_login_with_correct_pin_succeeds():
    response = client.post(
        "/api/v1/management/login",
        json={"pin": TEST_PIN, "manager_name": "Kuri"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["manager_name"] == "Kuri"
    assert "token" in body


def test_login_with_incorrect_pin_returns_401():
    response = client.post(
        "/api/v1/management/login",
        json={"pin": "wrong-pin", "manager_name": "Kuri"},
    )

    assert response.status_code == 401


def test_login_returns_503_when_pin_not_configured(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", None)

    response = client.post(
        "/api/v1/management/login",
        json={"pin": "anything", "manager_name": "Kuri"},
    )

    assert response.status_code == 503


def test_repeated_failed_logins_trigger_lockout(monkeypatch):
    monkeypatch.setattr(management_auth, "LOGIN_MAX_ATTEMPTS", 3)

    for _ in range(3):
        response = client.post(
            "/api/v1/management/login",
            json={"pin": "wrong", "manager_name": "Kuri"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/management/login",
        json={"pin": TEST_PIN, "manager_name": "Kuri"},
    )

    assert locked_response.status_code == 429


def test_logout_revokes_session():
    token = _login()

    response = client.post("/api/v1/management/logout", headers=_auth_headers(token))
    assert response.status_code == 200

    protected_response = client.get(
        "/api/v1/management/lines", headers=_auth_headers(token)
    )
    assert protected_response.status_code == 401


# ==========================================================
# UNAUTHORISED ACCESS
# ==========================================================


PROTECTED_ROUTES = [
    ("GET", "/api/v1/management/lines"),
    ("GET", "/api/v1/management/active-runs"),
    ("GET", "/api/v1/management/technician-performance"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_protected_endpoint_without_token_returns_401(method, path):
    response = client.request(method, path)
    assert response.status_code == 401


def test_protected_endpoint_with_invalid_token_returns_401():
    response = client.get(
        "/api/v1/management/lines",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401():
    token = _login()
    management_auth._sessions[token]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    response = client.get("/api/v1/management/lines", headers=_auth_headers(token))
    assert response.status_code == 401


# ==========================================================
# LINE CONFIGURATION
# ==========================================================


def test_list_lines_returns_items(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        management_api,
        "list_production_lines",
        lambda: [{"id": 1, "name": "Rovema", "active": True, "display_order": 1}],
    )

    response = client.get("/api/v1/management/lines", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Rovema"


def test_create_line_writes_audit_log(monkeypatch):
    token = _login()
    created_row = {"id": 5, "name": "NewLine", "active": True, "display_order": 0}
    monkeypatch.setattr(
        management_api, "create_production_line", lambda name, display_order: created_row
    )

    audit_calls = []
    monkeypatch.setattr(
        management_api, "insert_audit_log", lambda **kwargs: audit_calls.append(kwargs)
    )

    response = client.post(
        "/api/v1/management/lines",
        json={"name": "NewLine"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "NewLine"
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "create_line"
    assert audit_calls[0]["manager_name"] == "Kuri"
    assert audit_calls[0]["record_type"] == "production_line"
    assert audit_calls[0]["previous_value"] is None
    assert audit_calls[0]["new_value"]["name"] == "NewLine"


def test_create_line_rejects_blank_name():
    token = _login()

    response = client.post(
        "/api/v1/management/lines",
        json={"name": "   "},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_patch_line_returns_404_when_missing(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_production_line", lambda line_id: None)

    response = client.patch(
        "/api/v1/management/lines/999",
        json={"active": False},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_patch_line_success_writes_before_and_after(monkeypatch):
    token = _login()
    before = {"id": 1, "name": "Rovema", "active": True, "display_order": 1}
    after = {"id": 1, "name": "Rovema", "active": False, "display_order": 1}

    monkeypatch.setattr(management_api, "get_production_line", lambda line_id: before)
    monkeypatch.setattr(
        management_api,
        "update_production_line",
        lambda line_id, name, active, display_order: after,
    )

    audit_calls = []
    monkeypatch.setattr(
        management_api, "insert_audit_log", lambda **kwargs: audit_calls.append(kwargs)
    )

    response = client.patch(
        "/api/v1/management/lines/1",
        json={"active": False},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert audit_calls[0]["previous_value"]["active"] is True
    assert audit_calls[0]["new_value"]["active"] is False


# ==========================================================
# MACHINES
# ==========================================================


def test_create_machine(monkeypatch):
    token = _login()
    created = {
        "id": 10,
        "production_line_id": 1,
        "name": "BV1",
        "active": True,
        "display_order": 0,
    }
    monkeypatch.setattr(
        management_api, "create_machine", lambda line_id, name, display_order: created
    )
    monkeypatch.setattr(management_api, "insert_audit_log", lambda **kwargs: None)

    response = client.post(
        "/api/v1/management/lines/1/machines",
        json={"name": "BV1"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "BV1"


def test_patch_machine_returns_404_when_missing(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_machine", lambda machine_id: None)

    response = client.patch(
        "/api/v1/management/machines/999",
        json={"active": False},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


# ==========================================================
# FAULT / PLANNED-DOWNTIME BUTTONS
# ==========================================================


def test_create_fault_button(monkeypatch):
    token = _login()
    created = {
        "id": 20,
        "machine_id": 10,
        "name": "Film Jam",
        "event_type": "unplanned_fault",
        "ownership": "Production",
        "fault_category": None,
        "display_order": 0,
        "active": True,
    }
    monkeypatch.setattr(
        management_api,
        "create_button",
        lambda machine_id, name, event_type, ownership, fault_category, display_order: created,
    )
    monkeypatch.setattr(management_api, "insert_audit_log", lambda **kwargs: None)

    response = client.post(
        "/api/v1/management/machines/10/buttons",
        json={"name": "Film Jam", "event_type": "unplanned_fault", "ownership": "Production"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["event_type"] == "unplanned_fault"


def test_create_planned_downtime_button(monkeypatch):
    token = _login()
    created = {
        "id": 21,
        "machine_id": 10,
        "name": "Film Change",
        "event_type": "planned_downtime",
        "ownership": "Production",
        "fault_category": None,
        "display_order": 0,
        "active": True,
    }
    monkeypatch.setattr(
        management_api,
        "create_button",
        lambda machine_id, name, event_type, ownership, fault_category, display_order: created,
    )
    monkeypatch.setattr(management_api, "insert_audit_log", lambda **kwargs: None)

    response = client.post(
        "/api/v1/management/machines/10/buttons",
        json={
            "name": "Film Change",
            "event_type": "planned_downtime",
            "ownership": "Production",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["event_type"] == "planned_downtime"


def test_create_button_rejects_unknown_event_type():
    token = _login()

    response = client.post(
        "/api/v1/management/machines/10/buttons",
        json={"name": "X", "event_type": "not_a_type", "ownership": "Production"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_create_button_rejects_unknown_ownership():
    token = _login()

    response = client.post(
        "/api/v1/management/machines/10/buttons",
        json={"name": "X", "event_type": "unplanned_fault", "ownership": "Someone"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_patch_button_returns_404_when_missing(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_button", lambda button_id: None)

    response = client.patch(
        "/api/v1/management/buttons/999",
        json={"active": False},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_patch_button_can_disable(monkeypatch):
    token = _login()
    before = {
        "id": 20, "machine_id": 10, "name": "Film Jam", "event_type": "unplanned_fault",
        "ownership": "Production", "fault_category": None, "display_order": 0, "active": True,
    }
    after = {**before, "active": False}

    monkeypatch.setattr(management_api, "get_button", lambda button_id: before)
    monkeypatch.setattr(
        management_api,
        "update_button",
        lambda button_id, name, event_type, ownership, fault_category, display_order, active: after,
    )
    monkeypatch.setattr(management_api, "insert_audit_log", lambda **kwargs: None)

    response = client.patch(
        "/api/v1/management/buttons/20",
        json={"active": False},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False


# ==========================================================
# PUBLIC HMI CONFIG - DISABLED ROWS EXCLUDED
# ==========================================================


def test_public_hmi_config_query_filters_on_active_true():
    source = inspect.getsource(database.get_public_hmi_config)
    assert "pl.active = true" in source
    assert "m.active = true" in source
    assert "b.active = true" in source


def test_hmi_config_assembles_nested_tree(monkeypatch):
    rows = [
        {
            "line_id": 1, "line_name": "Rovema", "line_display_order": 1,
            "machine_id": 10, "machine_name": "BV1", "machine_display_order": 0,
            "button_id": 20, "button_name": "Film Jam", "event_type": "unplanned_fault",
            "ownership": "Production", "fault_category": None,
            "button_display_order": 0,
        },
        {
            "line_id": 1, "line_name": "Rovema", "line_display_order": 1,
            "machine_id": 10, "machine_name": "BV1", "machine_display_order": 0,
            "button_id": 21, "button_name": "Film Change", "event_type": "planned_downtime",
            "ownership": "Production", "fault_category": None,
            "button_display_order": 1,
        },
    ]
    monkeypatch.setattr(hmi_config_api, "get_public_hmi_config", lambda: rows)

    response = client.get("/api/v1/hmi/config")

    assert response.status_code == 200
    body = response.json()
    assert len(body["lines"]) == 1
    assert body["lines"][0]["name"] == "Rovema"
    assert len(body["lines"][0]["machines"]) == 1
    assert len(body["lines"][0]["machines"][0]["buttons"]) == 2


def test_hmi_config_requires_no_authentication():
    response = client.get("/api/v1/hmi/config")
    # No Authorization header sent - must not be rejected as unauthorised.
    assert response.status_code != 401


def test_hmi_config_returns_safe_error_on_database_failure(monkeypatch, capsys):
    def fake_get_config():
        raise RuntimeError("postgresql://user:s3cr3t@host/db failed")

    monkeypatch.setattr(hmi_config_api, "get_public_hmi_config", fake_get_config)

    response = client.get("/api/v1/hmi/config")

    assert response.status_code == 503
    captured = capsys.readouterr()
    assert "s3cr3t" not in response.text
    assert "s3cr3t" not in captured.out
    assert "s3cr3t" not in captured.err


# ==========================================================
# ACTIVE RUNS
# ==========================================================


def test_active_runs_listing(monkeypatch):
    token = _login()
    started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        management_api,
        "get_all_active_runs",
        lambda: [
            {
                "id": 24, "production_line": "GIC", "line_technician": "Marina",
                "shift": "Nights", "customer": "Tesco", "product": "White Basmati",
                "status": "Active", "started_at": started_at,
            }
        ],
    )

    response = client.get("/api/v1/management/active-runs", headers=_auth_headers(token))

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["id"] == 24
    assert items[0]["active_seconds"] > 0


# ==========================================================
# FORCE CLOSE
# ==========================================================


def test_force_close_returns_404_for_unknown_run(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_production_run_by_id", lambda run_id: None)

    response = client.post(
        "/api/v1/management/runs/999/force-close",
        json={"reason": "Technician left mid-shift"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_force_close_returns_409_for_completed_run(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        management_api,
        "get_production_run_by_id",
        lambda run_id: {"id": run_id, "production_line": "Rovema", "status": "Completed"},
    )

    response = client.post(
        "/api/v1/management/runs/10/force-close",
        json={"reason": "Production stopped"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_force_close_requires_reason():
    token = _login()

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_force_close_requires_note_when_reason_is_other():
    token = _login()

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={"reason": "Other"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_force_close_rejects_unknown_reason():
    token = _login()

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={"reason": "Not a real reason"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_force_close_success_writes_audit_log(monkeypatch):
    token = _login()
    before = {"id": 24, "production_line": "GIC", "status": "Active"}
    closed = {"id": 24, "production_line": "GIC", "status": "Cancelled", "finished_at": "now"}

    monkeypatch.setattr(management_api, "get_production_run_by_id", lambda run_id: before)
    monkeypatch.setattr(
        management_api, "force_close_production_run", lambda run_id, finished_at: closed
    )

    audit_calls = []
    monkeypatch.setattr(
        management_api, "insert_audit_log", lambda **kwargs: audit_calls.append(kwargs)
    )

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={"reason": "Technician left mid-shift"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 24
    assert body["run_status"] == "Cancelled"
    assert body["closed_by"] == "Kuri"

    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "force_close_run"
    assert audit_calls[0]["manager_name"] == "Kuri"
    assert audit_calls[0]["record_type"] == "production_run"
    assert audit_calls[0]["reason"] == "Technician left mid-shift"


def test_force_close_concurrent_protection_returns_409(monkeypatch):
    # Simulates: the run was Active when we looked it up, but another
    # manager's force-close committed first, so our atomic UPDATE
    # (WHERE status='Active') matches zero rows.
    token = _login()
    monkeypatch.setattr(
        management_api,
        "get_production_run_by_id",
        lambda run_id: {"id": run_id, "production_line": "GIC", "status": "Active"},
    )
    monkeypatch.setattr(
        management_api, "force_close_production_run", lambda run_id, finished_at: None
    )

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={"reason": "Duplicate run"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_force_close_returns_safe_error_on_database_failure(monkeypatch, capsys):
    token = _login()
    monkeypatch.setattr(
        management_api,
        "get_production_run_by_id",
        lambda run_id: {"id": run_id, "production_line": "GIC", "status": "Active"},
    )

    def fake_force_close(run_id, finished_at):
        raise RuntimeError("postgresql://user:s3cr3t@host/db failed")

    monkeypatch.setattr(management_api, "force_close_production_run", fake_force_close)

    response = client.post(
        "/api/v1/management/runs/24/force-close",
        json={"reason": "Production stopped"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 503
    captured = capsys.readouterr()
    assert "s3cr3t" not in response.text
    assert "s3cr3t" not in captured.out
    assert "s3cr3t" not in captured.err


# ==========================================================
# TECHNICIAN PERFORMANCE
# ==========================================================


def test_technician_performance_query_reuses_test_data_exclusion():
    source = inspect.getsource(database.get_technician_performance)
    assert "_run_conditions" in source
    assert "_hourly_conditions" in source
    assert "_fault_conditions" in source


def test_technician_performance_ranks_by_target_achievement_not_raw_output(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        management_api,
        "get_technician_performance",
        lambda filters: [
            {
                "line_technician": "Marina",
                "completed_runs": 5,
                "expected_pallets": 100.0,
                "actual_pallets": 60.0,
                "expected_tonnes": 10.0,
                "actual_tonnes": 6.0,
                "output_gap_pallets": 40.0,
                "output_gap_tonnes": 4.0,
                "target_achievement_percent": 60.0,
                "planned_downtime_minutes": 30.0,
                "unplanned_downtime_minutes": 10.0,
                "data_completion_rate_percent": 100.0,
                "lines": ["GIC"], "shifts": ["Nights"], "products": ["Basmati"],
                "customers": ["Tesco"], "run_ids": [1, 2, 3, 4, 5],
            },
            {
                # Fewer raw pallets than Marina, but a much higher
                # achievement percentage - must rank ABOVE Marina.
                "line_technician": "Ben",
                "completed_runs": 5,
                "expected_pallets": 50.0,
                "actual_pallets": 48.0,
                "expected_tonnes": 5.0,
                "actual_tonnes": 4.8,
                "output_gap_pallets": 2.0,
                "output_gap_tonnes": 0.2,
                "target_achievement_percent": 96.0,
                "planned_downtime_minutes": 10.0,
                "unplanned_downtime_minutes": 5.0,
                "data_completion_rate_percent": 100.0,
                "lines": ["Rovema"], "shifts": ["Days"], "products": ["Rice"],
                "customers": ["Asda"], "run_ids": [6, 7, 8, 9, 10],
            },
        ],
    )

    response = client.get(
        "/api/v1/management/technician-performance", headers=_auth_headers(token)
    )

    assert response.status_code == 200
    ranked = response.json()["ranked"]
    assert ranked[0]["line_technician"] == "Ben"
    assert ranked[0]["label"] == "On target"
    assert ranked[1]["line_technician"] == "Marina"
    assert ranked[1]["label"] == "Needs review"


def test_technician_performance_below_minimum_sample_is_not_ranked(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "MIN_SAMPLE_RUNS", 3)
    monkeypatch.setattr(
        management_api,
        "get_technician_performance",
        lambda filters: [
            {
                "line_technician": "NewTechnician",
                "completed_runs": 1,
                "expected_pallets": 10.0, "actual_pallets": 10.0,
                "expected_tonnes": 1.0, "actual_tonnes": 1.0,
                "output_gap_pallets": 0.0, "output_gap_tonnes": 0.0,
                "target_achievement_percent": 100.0,
                "planned_downtime_minutes": 0.0, "unplanned_downtime_minutes": 0.0,
                "data_completion_rate_percent": 100.0,
                "lines": ["GIC"], "shifts": ["Nights"], "products": ["Basmati"],
                "customers": ["Tesco"], "run_ids": [1],
            },
        ],
    )

    response = client.get(
        "/api/v1/management/technician-performance", headers=_auth_headers(token)
    )

    body = response.json()
    assert body["ranked"] == []
    assert len(body["insufficient_data"]) == 1
    assert body["insufficient_data"][0]["label"] == "Insufficient data"


def test_technician_performance_missing_expected_data_is_null_not_zero(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "MIN_SAMPLE_RUNS", 1)
    monkeypatch.setattr(
        management_api,
        "get_technician_performance",
        lambda filters: [
            {
                "line_technician": "NoDataYet",
                "completed_runs": 2,
                "expected_pallets": 0.0, "actual_pallets": 0.0,
                "expected_tonnes": 0.0, "actual_tonnes": 0.0,
                "output_gap_pallets": 0.0, "output_gap_tonnes": 0.0,
                "target_achievement_percent": None,
                "planned_downtime_minutes": 0.0, "unplanned_downtime_minutes": 0.0,
                "data_completion_rate_percent": None,
                "lines": ["GIC"], "shifts": ["Nights"], "products": ["Basmati"],
                "customers": ["Tesco"], "run_ids": [1, 2],
            },
        ],
    )

    response = client.get(
        "/api/v1/management/technician-performance", headers=_auth_headers(token)
    )

    entry = response.json()["ranked"][0]
    assert entry["target_achievement_percent"] is None
    assert entry["label"] == "Insufficient data"
    assert entry["data_completion_rate_percent"] is None


def test_technician_performance_shows_selected_date_range(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_technician_performance", lambda filters: [])

    response = client.get(
        "/api/v1/management/technician-performance"
        "?date_from=2026-01-01&date_to=2026-01-31",
        headers=_auth_headers(token),
    )

    body = response.json()
    assert body["date_from"] == "2026-01-01"
    assert body["date_to"] == "2026-01-31"
    assert body["period"] == "custom"


def test_technician_performance_resolves_named_period(monkeypatch):
    token = _login()
    monkeypatch.setattr(management_api, "get_technician_performance", lambda filters: [])

    response = client.get(
        "/api/v1/management/technician-performance?period=today",
        headers=_auth_headers(token),
    )

    body = response.json()
    assert body["date_from"] == body["date_to"]
    assert body["period"] == "today"


# ==========================================================
# ALL TEN SUGGESTED MANAGEMENT ROUTES + PUBLIC CONFIG REGISTERED
# ==========================================================


def test_all_management_routes_are_registered():
    paths = set(app.openapi()["paths"].keys())
    for expected in [
        "/api/v1/management/login",
        "/api/v1/management/logout",
        "/api/v1/management/lines",
        "/api/v1/management/lines/{line_id}",
        "/api/v1/management/lines/{line_id}/machines",
        "/api/v1/management/machines/{machine_id}",
        "/api/v1/management/machines/{machine_id}/buttons",
        "/api/v1/management/buttons/{button_id}",
        "/api/v1/management/active-runs",
        "/api/v1/management/runs/{run_id}/force-close",
        "/api/v1/management/technician-performance",
        "/api/v1/hmi/config",
    ]:
        assert expected in paths, f"missing route: {expected}"


# ==========================================================
# CORS
# ==========================================================


def test_cors_preflight_allows_patch_and_authorization_header():
    response = client.options(
        "/api/v1/management/lines/1",
        headers={
            "Origin": DASHBOARD_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DASHBOARD_ORIGIN


def test_cors_rejects_other_origins_on_management_routes():
    response = client.options(
        "/api/v1/management/lines",
        headers={
            "Origin": "https://some-other-site.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
