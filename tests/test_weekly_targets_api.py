"""
Offline tests for the Management weekly tonnage target endpoints in
src/management_api.py. Every database function is monkeypatched where
management_api imported it; no Supabase connection is opened.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import management_api, management_auth
from src.api import app


TEST_PIN = "test-management-pin-0000"
SECRET = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", TEST_PIN)
    management_auth._sessions.clear()
    token = management_auth.create_session("Kuri")["token"]
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"})
    management_auth._sessions.clear()


@pytest.fixture
def audit(monkeypatch):
    entries = []
    monkeypatch.setattr(management_api, "insert_audit_log", lambda **entry: entries.append(entry))
    return entries


def saved_row(scope, line, tonnes):
    return {
        "id": 1, "week_start": date(2026, 1, 12), "scope": scope, "production_line": line,
        "target_tonnes": Decimal(tonnes), "set_by": "Kuri",
        "created_at": datetime(2026, 1, 12, 7, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 12, 7, tzinfo=timezone.utc),
    }


ALL_FOUR = {
    "week_start": "2026-01-12",
    "targets": [
        {"scope": "site", "target_tonnes": 400},
        {"scope": "line", "production_line": "Rovema", "target_tonnes": 150},
        {"scope": "line", "production_line": "GIC", "target_tonnes": 150.5},
        {"scope": "line", "production_line": "Guill", "target_tonnes": 99.125},
    ],
}


def test_weekly_target_routes_require_a_management_session():
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/management/weekly-targets").status_code == 401
    assert anonymous.post("/api/v1/management/weekly-targets", json=ALL_FOUR).status_code == 401


def test_set_site_and_all_three_line_targets_with_audit(client, audit, monkeypatch):
    received = {}

    def fake_upsert(week_start, targets, set_by):
        received.update(week_start=week_start, targets=targets, set_by=set_by)
        previous = saved_row("site", None, 350)
        return [
            (previous if t["scope"] == "site" else None,
             saved_row(t["scope"], t["production_line"], t["target_tonnes"]))
            for t in targets
        ]

    monkeypatch.setattr(management_api, "upsert_weekly_targets", fake_upsert)

    response = client.post("/api/v1/management/weekly-targets", json=ALL_FOUR)

    assert response.status_code == 200
    assert received["week_start"] == date(2026, 1, 12)
    assert received["set_by"] == "Kuri"
    assert [t["target_tonnes"] for t in received["targets"]] == [
        Decimal(400), Decimal(150), Decimal("150.5"), Decimal("99.125"),
    ]
    body = response.json()
    assert body["week"]["start"] == "2026-01-12T06:00:00+00:00"
    assert body["week"]["end"] == "2026-01-19T06:00:00+00:00"
    assert len(body["targets"]) == 4

    assert len(audit) == 4
    assert audit[0]["action"] == "set_weekly_tonnage_target"
    assert audit[0]["record_id"] == "2026-01-12:site:site"
    assert audit[0]["previous_value"]["target_tonnes"] == 350.0
    assert audit[1]["previous_value"] is None
    assert audit[1]["record_id"] == "2026-01-12:line:Rovema"


def test_week_defaults_to_the_current_production_week(client, audit, monkeypatch):
    received = {}

    def fake_upsert(week_start, targets, set_by):
        received["week_start"] = week_start
        return [(None, saved_row("site", None, 400))]

    monkeypatch.setattr(management_api, "upsert_weekly_targets", fake_upsert)
    monkeypatch.setattr(management_api, "production_week_start_date", lambda now: date(2026, 9, 21))

    response = client.post(
        "/api/v1/management/weekly-targets", json={"targets": [{"scope": "site", "target_tonnes": 400}]}
    )

    assert response.status_code == 200
    assert received["week_start"] == date(2026, 9, 21)


@pytest.mark.parametrize(
    "payload",
    [
        {"week_start": "2026-01-13", "targets": [{"scope": "site", "target_tonnes": 400}]},
        {"targets": []},
        {"targets": [{"scope": "site", "target_tonnes": 0}]},
        {"targets": [{"scope": "site", "target_tonnes": -5}]},
        {"targets": [{"scope": "site", "target_tonnes": 1.0005}]},
        {"targets": [{"scope": "site", "production_line": "GIC", "target_tonnes": 5}]},
        {"targets": [{"scope": "line", "target_tonnes": 5}]},
        {"targets": [{"scope": "line", "production_line": "Nowhere", "target_tonnes": 5}]},
        {"targets": [{"scope": "shift", "target_tonnes": 5}]},
        {"targets": [{"scope": "site", "target_tonnes": 5}, {"scope": "site", "target_tonnes": 6}]},
    ],
)
def test_invalid_weekly_targets_are_422_and_never_saved(payload, client, audit, monkeypatch):
    calls = []
    monkeypatch.setattr(management_api, "upsert_weekly_targets", lambda *a: calls.append(a))

    response = client.post("/api/v1/management/weekly-targets", json=payload)

    assert response.status_code == 422
    assert calls == []
    assert audit == []


def test_get_weekly_targets(client, monkeypatch):
    monkeypatch.setattr(
        management_api, "list_weekly_targets", lambda week_start: [saved_row("line", "GIC", "150.500")]
    )

    response = client.get("/api/v1/management/weekly-targets", params={"week_start": "2026-01-12"})

    assert response.status_code == 200
    target = response.json()["targets"][0]
    assert target["scope"] == "line"
    assert target["production_line"] == "GIC"
    assert target["target_tonnes"] == 150.5
    assert target["set_by"] == "Kuri"


def test_get_weekly_targets_rejects_non_monday(client):
    response = client.get("/api/v1/management/weekly-targets", params={"week_start": "2026-01-14"})
    assert response.status_code == 422


def test_weekly_target_database_failure_is_safe_503(client, audit, monkeypatch, capsys):
    def broken(*args):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(management_api, "upsert_weekly_targets", broken)

    response = client.post("/api/v1/management/weekly-targets", json=ALL_FOUR)

    assert response.status_code == 503
    captured = capsys.readouterr()
    assert "s3cr3t" not in response.text + captured.out + captured.err
    assert audit == []
