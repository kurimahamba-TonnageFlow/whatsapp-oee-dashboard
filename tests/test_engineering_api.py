"""
Offline tests for the Engineering API (src/engineering_api.py) and its
auth module (src/engineering_auth.py), composed onto the app in
src/api.py.

Never touches Supabase: every src.database function engineering_api
imported is monkeypatched at the point where it imported it (same
pattern as tests/test_management_api.py). The two "atomicity" tests
near the bottom monkeypatch src.database.get_database_connection
itself with a fake connection/cursor double, so the transaction logic
inside database.close_engineering_fault is verified directly, offline.
"""

import ast
from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src import database, engineering_api, engineering_auth, management_auth
from src.api import app
from src.domain_constants import ENGINEERS


client = TestClient(app)

TEST_PIN = "test-engineering-pin-0000"


@pytest.fixture(autouse=True)
def reset_auth_state(monkeypatch):
    monkeypatch.setattr(engineering_auth, "ENGINEERING_PIN", TEST_PIN)
    engineering_auth._sessions.clear()
    engineering_auth._login_attempts.clear()
    # Cleared too, since a couple of tests below deliberately create a
    # Management session to prove cross-auth isolation - never leak
    # state into (or out of) this file's own Management usage.
    management_auth._sessions.clear()
    management_auth._login_attempts.clear()
    yield


def _login(engineer_name="Alfie"):
    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": engineer_name},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _dt(offset_minutes=0):
    return datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


def _downtime_event_row(**overrides):
    row = {
        "id": 12,
        "production_run_id": 40,
        "fault_id": 3,
        "machine": "BV1",
        "reason": "Film Jam",
        "reported_by": "Marina",
        "engineer": "Alfie",
        "production_status": "Ongoing",
        "engineering_status": "Investigating",
        "opened_at": _dt(),
        "accepted_at": _dt(5),
        "resolved_at": None,
    }
    row.update(overrides)
    return row


def _repair_update_row(**overrides):
    row = {
        "id": 1,
        "engineer": "Alfie",
        "update_type": "Follow Up",
        "repair_classification": "Mechanical",
        "finding": "Film sensor misaligned",
        "action": "Realigned and tested",
        "notes": None,
        "setting_name": None,
        "previous_value": None,
        "new_value": None,
        "reason_for_change": None,
        "affected_products_or_formats": None,
        "engineering_status": "Investigating",
        "created_at": _dt(20),
    }
    row.update(overrides)
    return row


def _fault_row(**overrides):
    row = {
        "downtime_event_id": 12,
        "production_run_id": 40,
        "production_line": "Rovema",
        "fault_id": 3,
        "machine": "BV1",
        "reason": "Film Jam",
        "reported_by": "Marina",
        "engineer": None,
        "production_status": "Ongoing",
        "engineering_status": "Not Started",
        "opened_at": _dt(),
        "accepted_at": None,
        "resolved_at": None,
        "duration_minutes": 12.5,
        "duration_is_active": True,
        "repair_updates": [],
    }
    row.update(overrides)
    return row


MECHANICAL_PAYLOAD = {
    "classification": "Mechanical",
    "finding": "Film sensor misaligned",
    "action": "Realigned and tested",
}

MACHINE_SETTING_PAYLOAD = {
    "classification": "Machine Setting",
    "finding": "Seal failing at low line speed",
    "action": "Increased sealer temperature",
    "setting_name": "Sealer temperature",
    "previous_value": "185C",
    "new_value": "192C",
    "reason_for_change": "Seal integrity failing at low line speed",
    "affected_products_or_formats": "1kg Pillow Pack - all customers",
}


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================


def test_login_with_correct_pin_succeeds():
    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": "Alfie"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["engineer_name"] == "Alfie"
    assert "token" in body


def test_login_with_incorrect_pin_returns_401():
    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": "wrong-pin", "engineer_name": "Alfie"},
    )

    assert response.status_code == 401


def test_login_rejects_unknown_engineer():
    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": "NotARealEngineer"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("engineer_name", list(ENGINEERS))
def test_login_accepts_each_approved_engineer(engineer_name):
    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": engineer_name},
    )

    assert response.status_code == 200
    assert response.json()["engineer_name"] == engineer_name


def test_login_returns_503_when_pin_not_configured(monkeypatch):
    monkeypatch.setattr(engineering_auth, "ENGINEERING_PIN", None)

    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": "anything", "engineer_name": "Alfie"},
    )

    assert response.status_code == 503


def test_repeated_failed_logins_trigger_lockout(monkeypatch):
    monkeypatch.setattr(engineering_auth, "LOGIN_MAX_ATTEMPTS", 3)

    for _ in range(3):
        response = client.post(
            "/api/v1/engineering/login",
            json={"pin": "wrong", "engineer_name": "Alfie"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": "Alfie"},
    )

    assert locked_response.status_code == 429


def test_lockout_expires_after_window(monkeypatch):
    monkeypatch.setattr(engineering_auth, "LOGIN_MAX_ATTEMPTS", 3)

    for _ in range(3):
        client.post(
            "/api/v1/engineering/login",
            json={"pin": "wrong", "engineer_name": "Alfie"},
        )

    assert client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": "Alfie"},
    ).status_code == 429

    # Simulate the lockout window naturally elapsing.
    for record in engineering_auth._login_attempts.values():
        record["locked_until"] = datetime.now(timezone.utc) - timedelta(minutes=1)

    response = client.post(
        "/api/v1/engineering/login",
        json={"pin": TEST_PIN, "engineer_name": "Alfie"},
    )

    assert response.status_code == 200


def test_logout_revokes_session():
    token = _login()

    response = client.post("/api/v1/engineering/logout", headers=_auth_headers(token))
    assert response.status_code == 200

    protected_response = client.get(
        "/api/v1/engineering/faults", headers=_auth_headers(token)
    )
    assert protected_response.status_code == 401


# ==========================================================
# SESSION VALIDATION / CROSS-AUTH ISOLATION
# ==========================================================


def test_protected_endpoint_without_token_returns_401():
    response = client.get("/api/v1/engineering/faults")
    assert response.status_code == 401


def test_protected_endpoint_with_invalid_token_returns_401():
    response = client.get(
        "/api/v1/engineering/faults",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401():
    token = _login()
    engineering_auth._sessions[token]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))
    assert response.status_code == 401


def test_engineering_token_rejected_by_management_endpoints():
    token = _login()

    response = client.get("/api/v1/management/lines", headers=_auth_headers(token))
    assert response.status_code == 401


def test_management_token_rejected_by_engineering_endpoints(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", "mgmt-test-pin-0000")

    mgmt_login = client.post(
        "/api/v1/management/login",
        json={"pin": "mgmt-test-pin-0000", "manager_name": "Kuri"},
    )
    assert mgmt_login.status_code == 200
    mgmt_token = mgmt_login.json()["token"]

    response = client.get(
        "/api/v1/engineering/faults", headers=_auth_headers(mgmt_token)
    )
    assert response.status_code == 401


def test_no_secret_values_in_error_responses_or_logs(monkeypatch, capsys):
    token = _login()

    def fake_get_engineering_faults(filters):
        raise RuntimeError(f"postgresql://user:{TEST_PIN}@host/db failed")

    monkeypatch.setattr(engineering_api, "get_engineering_faults", fake_get_engineering_faults)

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))

    assert response.status_code == 503
    captured = capsys.readouterr()
    assert TEST_PIN not in response.text
    assert TEST_PIN not in captured.out
    assert TEST_PIN not in captured.err
    assert token not in response.text


# ==========================================================
# FAULT LISTING
# ==========================================================


def test_faults_listing_returns_items(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_engineering_faults", lambda filters: [_fault_row()]
    )

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["machine"] == "BV1"


def test_faults_listing_empty(monkeypatch):
    token = _login()
    monkeypatch.setattr(engineering_api, "get_engineering_faults", lambda filters: [])

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_faults_listing_open_and_resolved_shapes(monkeypatch):
    token = _login()
    open_fault = _fault_row(
        downtime_event_id=1,
        production_status="Ongoing",
        engineering_status="Investigating",
        engineer="Alfie",
        accepted_at=_dt(5),
        repair_updates=[_repair_update_row()],
    )
    resolved_fault = _fault_row(
        downtime_event_id=2,
        production_status="Resolved",
        engineering_status="Resolved",
        engineer="Dan",
        accepted_at=_dt(5),
        resolved_at=_dt(60),
        duration_is_active=False,
        repair_updates=[
            _repair_update_row(
                id=2,
                engineer="Dan",
                update_type="Resolution",
                repair_classification="Machine Setting",
                setting_name="Sealer temperature",
                previous_value="185C",
                new_value="192C",
                reason_for_change="Seal integrity failing",
                affected_products_or_formats="1kg Pillow Pack",
            )
        ],
    )
    monkeypatch.setattr(
        engineering_api, "get_engineering_faults", lambda filters: [open_fault, resolved_fault]
    )

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["production_status"] == "Ongoing"
    assert items[0]["resolved_at"] is None
    assert items[1]["production_status"] == "Resolved"
    assert items[1]["resolved_at"] is not None
    assert items[1]["repair_updates"][0]["repair_classification"] == "Machine Setting"


def test_repair_update_created_at_is_a_required_field():
    # Corrected assumption: a live-schema preflight confirmed
    # engineering_updates.created_at is NOT NULL DEFAULT now() for
    # every row already in the database - there is no "historical,
    # unknown timestamp" case here, so the response model must reject
    # a missing/None value rather than silently accept it.
    with pytest.raises(ValidationError):
        engineering_api.EngineeringFaultRepairUpdate(**_repair_update_row(created_at=None))


def test_faults_listing_serialises_repair_update_with_real_created_at(monkeypatch):
    token = _login()
    fault = _fault_row(repair_updates=[_repair_update_row(created_at=_dt(20))])
    monkeypatch.setattr(engineering_api, "get_engineering_faults", lambda filters: [fault])

    response = client.get("/api/v1/engineering/faults", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["items"][0]["repair_updates"][0]["created_at"] is not None


# ==========================================================
# ACCEPT / START WORK
# ==========================================================


def test_accept_success(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(engineer=None, engineering_status="Not Started"),
    )
    monkeypatch.setattr(
        engineering_api,
        "accept_engineering_fault",
        lambda downtime_event_id, engineer, accepted_at: _downtime_event_row(),
    )

    response = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["engineer"] == "Alfie"
    assert body["engineering_status"] == "Investigating"


def test_accept_unknown_fault_returns_404(monkeypatch):
    token = _login()
    monkeypatch.setattr(engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: None)

    response = client.post("/api/v1/engineering/faults/999/accept", headers=_auth_headers(token))

    assert response.status_code == 404


def test_accept_resolved_fault_returns_409(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(production_status="Resolved"),
    )

    response = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(token))

    assert response.status_code == 409


def test_accept_same_engineer_repeat_is_idempotent(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(),
    )
    monkeypatch.setattr(
        engineering_api,
        "accept_engineering_fault",
        lambda downtime_event_id, engineer, accepted_at: _downtime_event_row(),
    )

    first = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(token))
    second = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["accepted_at"] == second.json()["accepted_at"]


def test_accept_second_engineer_cannot_overwrite_first(monkeypatch):
    dan_token = _login("Dan")
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(engineer="Alfie"),
    )
    monkeypatch.setattr(
        engineering_api,
        "accept_engineering_fault",
        lambda downtime_event_id, engineer, accepted_at: None,
    )

    response = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(dan_token))

    assert response.status_code == 409
    assert "already been accepted" in response.json()["detail"]


def test_accept_concurrent_protection_returns_409(monkeypatch):
    # Simulates: the fault was Ongoing and unassigned when we looked it
    # up, but another engineer's accept committed first, so our atomic
    # UPDATE (WHERE engineer IS NULL OR engineer = ours) matches zero
    # rows - the same idiom already proven by
    # test_management_api.test_force_close_concurrent_protection_returns_409.
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(engineer=None),
    )
    monkeypatch.setattr(
        engineering_api,
        "accept_engineering_fault",
        lambda downtime_event_id, engineer, accepted_at: None,
    )

    response = client.post("/api/v1/engineering/faults/12/accept", headers=_auth_headers(token))

    assert response.status_code == 409


# ==========================================================
# REPAIR UPDATES
# ==========================================================


def test_update_mechanical_success(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: _downtime_event_row()
    )
    monkeypatch.setattr(
        engineering_api,
        "add_engineering_repair_update",
        lambda downtime_event_id, repair_update: {"id": 9, "created_at": _dt(20)},
    )

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["engineering_update_id"] == 9


def test_update_response_always_includes_a_real_server_timestamp(monkeypatch):
    # A repair update created through this API always gets a real
    # timestamp - add_engineering_repair_update()'s INSERT relies on
    # engineering_updates.created_at's existing, verified-live
    # DEFAULT now(), so EngineeringUpdateResponse.created_at stays a
    # required, non-nullable field.
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: _downtime_event_row()
    )
    monkeypatch.setattr(
        engineering_api,
        "add_engineering_repair_update",
        lambda downtime_event_id, repair_update: {"id": 9, "created_at": _dt(20)},
    )

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["created_at"] is not None


def test_update_machine_setting_success(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: _downtime_event_row()
    )
    monkeypatch.setattr(
        engineering_api,
        "add_engineering_repair_update",
        lambda downtime_event_id, repair_update: {"id": 10, "created_at": _dt(21)},
    )

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json=MACHINE_SETTING_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["engineering_update_id"] == 10


def test_update_machine_setting_missing_fields_rejected():
    token = _login()

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json={
            "classification": "Machine Setting",
            "finding": "Seal failing",
            "action": "Adjusted temperature",
            # setting_name, previous_value, new_value, reason_for_change,
            # affected_products_or_formats all omitted.
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_update_mechanical_rejects_machine_setting_fields():
    token = _login()

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json={**MECHANICAL_PAYLOAD, "setting_name": "Sealer temperature"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_update_invalid_classification_rejected():
    token = _login()

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json={**MECHANICAL_PAYLOAD, "classification": "Electrical"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_update_rejects_blank_finding():
    token = _login()

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json={**MECHANICAL_PAYLOAD, "finding": "   "},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_update_unknown_fault_returns_404(monkeypatch):
    token = _login()
    monkeypatch.setattr(engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: None)

    response = client.post(
        "/api/v1/engineering/faults/999/updates",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_update_resolved_fault_returns_409(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(production_status="Resolved"),
    )

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_update_wrong_engineer_rejected(monkeypatch):
    dan_token = _login("Dan")
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(engineer="Alfie"),
    )

    response = client.post(
        "/api/v1/engineering/faults/12/updates",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(dan_token),
    )

    assert response.status_code == 409


# ==========================================================
# CLOSE FAULT
# ==========================================================


def test_close_mechanical_success(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: _downtime_event_row()
    )
    closed_row = _downtime_event_row(
        production_status="Resolved", engineering_status="Resolved", resolved_at=_dt(60)
    )
    monkeypatch.setattr(
        engineering_api,
        "close_engineering_fault",
        lambda downtime_event_id, repair_update, resolved_at: closed_row,
    )

    response = client.post(
        "/api/v1/engineering/faults/12/close",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["production_status"] == "Resolved"
    assert body["engineering_status"] == "Resolved"
    assert body["resolved_at"] is not None


def test_close_machine_setting_success(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: _downtime_event_row()
    )
    closed_row = _downtime_event_row(
        production_status="Resolved", engineering_status="Resolved", resolved_at=_dt(60)
    )
    monkeypatch.setattr(
        engineering_api,
        "close_engineering_fault",
        lambda downtime_event_id, repair_update, resolved_at: closed_row,
    )

    response = client.post(
        "/api/v1/engineering/faults/12/close",
        json=MACHINE_SETTING_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["production_status"] == "Resolved"


def test_close_missing_final_repair_details_rejected():
    token = _login()

    response = client.post(
        "/api/v1/engineering/faults/12/close",
        json={"classification": "Mechanical", "finding": "", "action": "Fixed it"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_close_wrong_engineer_rejected(monkeypatch):
    dan_token = _login("Dan")
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(engineer="Alfie"),
    )

    response = client.post(
        "/api/v1/engineering/faults/12/close",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(dan_token),
    )

    assert response.status_code == 409


def test_close_unknown_fault_returns_404(monkeypatch):
    token = _login()
    monkeypatch.setattr(engineering_api, "get_downtime_event_by_id", lambda downtime_event_id: None)

    response = client.post(
        "/api/v1/engineering/faults/999/close",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_close_already_resolved_fault_returns_409(monkeypatch):
    token = _login()
    monkeypatch.setattr(
        engineering_api,
        "get_downtime_event_by_id",
        lambda downtime_event_id: _downtime_event_row(production_status="Resolved"),
    )

    response = client.post(
        "/api/v1/engineering/faults/12/close",
        json=MECHANICAL_PAYLOAD,
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_close_duplicate_does_not_call_database_twice(monkeypatch):
    token = _login()
    calls = []

    state = {"status": "Ongoing"}

    def fake_get_downtime_event(downtime_event_id):
        return _downtime_event_row(production_status=state["status"])

    def fake_close(downtime_event_id, repair_update, resolved_at):
        calls.append(1)
        state["status"] = "Resolved"
        return _downtime_event_row(production_status="Resolved", engineering_status="Resolved", resolved_at=_dt(60))

    monkeypatch.setattr(engineering_api, "get_downtime_event_by_id", fake_get_downtime_event)
    monkeypatch.setattr(engineering_api, "close_engineering_fault", fake_close)

    first = client.post(
        "/api/v1/engineering/faults/12/close", json=MECHANICAL_PAYLOAD, headers=_auth_headers(token)
    )
    second = client.post(
        "/api/v1/engineering/faults/12/close", json=MECHANICAL_PAYLOAD, headers=_auth_headers(token)
    )

    assert first.status_code == 200
    # The second call's pre-check sees the fault is already Resolved
    # and is rejected with 409 before close_engineering_fault (and
    # therefore any duplicate final-repair INSERT) is ever attempted.
    assert second.status_code == 409
    assert len(calls) == 1


# ==========================================================
# DATABASE-LAYER ATOMICITY (close_engineering_fault)
# ==========================================================
#
# These two tests exercise src/database.py's close_engineering_fault
# directly, with a fake connection/cursor double standing in for
# psycopg - proving the transaction logic (single connection, explicit
# commit only on success, explicit rollback - discarding the INSERT
# too - when the guarded UPDATE matches zero rows) without a real
# database.


class _FakeCursor:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return self._results.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, results):
        self._cursor = _FakeCursor(results)
        self.committed = False
        self.rolled_back = False

    def cursor(self, row_factory=None):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


REPAIR_UPDATE_FIXTURE = {
    "production_run_id": 40,
    "fault_id": 3,
    "engineer": "Alfie",
    "repair_classification": "Mechanical",
    "finding": "Film sensor misaligned",
    "action": "Realigned and tested",
    "notes": None,
    "setting_name": None,
    "previous_value": None,
    "new_value": None,
    "reason_for_change": None,
    "affected_products_or_formats": None,
}


def test_close_engineering_fault_commits_once_on_success(monkeypatch):
    closed_row = {
        "id": 12, "production_run_id": 40, "fault_id": 3, "machine": "BV1",
        "reason": "Film Jam", "reported_by": "Marina", "engineer": "Alfie",
        "production_status": "Resolved", "engineering_status": "Resolved",
        "opened_at": _dt(), "accepted_at": _dt(5), "resolved_at": _dt(60),
    }
    fake_connection = _FakeConnection(results=[{"id": 99}, closed_row])
    monkeypatch.setattr(database, "get_database_connection", lambda: fake_connection)

    result = database.close_engineering_fault(12, REPAIR_UPDATE_FIXTURE, "2026-09-17T15:00:00+00:00")

    assert result == closed_row
    assert fake_connection.committed is True
    assert fake_connection.rolled_back is False


def test_close_engineering_fault_rolls_back_insert_when_already_resolved(monkeypatch):
    # The INSERT (final repair row) "succeeds" (returns an id), but the
    # guarded UPDATE matches zero rows - a racing request already
    # resolved this fault. The whole transaction, including the
    # INSERT, must be rolled back: no orphan final repair record, and
    # commit() must never be called.
    fake_connection = _FakeConnection(results=[{"id": 99}, None])
    monkeypatch.setattr(database, "get_database_connection", lambda: fake_connection)

    result = database.close_engineering_fault(12, REPAIR_UPDATE_FIXTURE, "2026-09-17T15:00:00+00:00")

    assert result is None
    assert fake_connection.rolled_back is True
    assert fake_connection.committed is False


def test_accept_engineering_fault_query_is_guarded():
    source = inspect.getsource(database.accept_engineering_fault)
    assert "production_status = 'Ongoing'" in source
    assert "engineer IS NULL OR engineer = %(engineer)s" in source


def test_close_engineering_fault_query_is_guarded():
    source = inspect.getsource(database.close_engineering_fault)
    assert "production_status = 'Ongoing'" in source


# ==========================================================
# update_type VOCABULARY (live constraint chk_engineering_update_type
# permits 'Investigation', 'Follow Up', 'Resolution' - verified by
# Supabase preflight; this API must only ever write the two it uses)
# ==========================================================


def test_add_engineering_repair_update_writes_follow_up():
    source = inspect.getsource(database.add_engineering_repair_update)
    assert "'Follow Up'" in source


def test_close_engineering_fault_writes_resolution():
    source = inspect.getsource(database.close_engineering_fault)
    assert "'Resolution'" in source


# ==========================================================
# MIGRATION 0002 - DOES NOT TOUCH created_at OR update_type
# (both already exist / are already correct in the live schema)
# ==========================================================


def _migration_0002_text():
    return Path(PROJECT_ROOT, "migrations", "0002_engineering_workflow.sql").read_text(
        encoding="utf-8"
    )


def test_migration_0002_does_not_add_created_at_column():
    text = _migration_0002_text()
    assert "ADD COLUMN created_at" not in text


def test_migration_0002_does_not_alter_created_at():
    text = _migration_0002_text()
    assert "ALTER COLUMN created_at" not in text


def test_migration_0002_does_not_change_update_type_constraint():
    # chk_engineering_update_type is allowed to be MENTIONED in an
    # explanatory comment (documenting that it already exists and is
    # left alone) - what must never appear is a statement that adds,
    # drops or otherwise modifies it or the update_type column itself.
    text = _migration_0002_text()
    assert "ADD CONSTRAINT chk_engineering_update_type" not in text
    assert "DROP CONSTRAINT chk_engineering_update_type" not in text
    assert "ALTER COLUMN update_type" not in text


# ==========================================================
# IMPORT SAFETY - NO DEPENDENCY ON src.main (Correction 1)
# ==========================================================
#
# src/main.py is the interactive console CLI (input()-driven) and
# must stay outside the HTTP API's import path. Two independent
# checks: a static one (the source text of engineering_api.py never
# references main.py) and a dynamic one (importing engineering_api in
# a fresh, isolated process never causes src.main / main to appear in
# sys.modules). Either alone could miss a regression the other would
# catch - e.g. a future re-export would fool the static check, and a
# transitive import through a third module would only show up
# dynamically.


def test_engineering_api_source_has_no_main_import():
    source = Path(PROJECT_ROOT, "src", "engineering_api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    referenced_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            referenced_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                referenced_modules.add(alias.name)

    assert "main" not in referenced_modules
    assert ".main" not in referenced_modules


def test_engineering_api_import_does_not_import_main_isolated_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "import src.engineering_api; "
            "assert 'src.main' not in sys.modules, 'src.main was imported'; "
            "assert 'main' not in sys.modules, 'main was imported'; "
            "print('IMPORT_OK')",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "IMPORT_OK" in result.stdout


# ==========================================================
# ALL SIX ENGINEERING ROUTES REGISTERED
# ==========================================================


def test_all_engineering_routes_are_registered():
    paths = set(app.openapi()["paths"].keys())
    for expected in [
        "/api/v1/engineering/login",
        "/api/v1/engineering/logout",
        "/api/v1/engineering/faults",
        "/api/v1/engineering/faults/{downtime_event_id}/accept",
        "/api/v1/engineering/faults/{downtime_event_id}/updates",
        "/api/v1/engineering/faults/{downtime_event_id}/close",
    ]:
        assert expected in paths, f"missing route: {expected}"
