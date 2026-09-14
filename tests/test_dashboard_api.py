"""
Offline tests for the Dashboard Read API in src/dashboard_api.py,
composed onto the main app in src/api.py.

These tests never touch Supabase: every src.database dashboard function
is monkeypatched at the point where src/dashboard_api.py imported it.
The test-data exclusion rule itself is verified structurally, against
the SQL condition-builder helpers in src/database.py, rather than
against a live table.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import dashboard_api, database
from src.api import DASHBOARD_ORIGIN, HMI_ORIGIN, app


client = TestClient(app)


def _dt(hour=8):
    return datetime(2026, 1, 1, hour, 0, 0, tzinfo=timezone.utc)


# ==========================================================
# ALL TEN ROUTES ARE REGISTERED
# ==========================================================


def test_all_ten_dashboard_routes_are_registered():
    # app.routes wraps included routers opaquely on this FastAPI version
    # (no flattened path/methods per route), so the generated OpenAPI
    # schema - which FastAPI resolves through those wrappers itself -
    # is the version-independent way to confirm registration.
    expected = {
        "/api/v1/dashboard/summary",
        "/api/v1/dashboard/runs",
        "/api/v1/dashboard/output-timeline",
        "/api/v1/dashboard/planned-downtime",
        "/api/v1/dashboard/engineering-downtime",
        "/api/v1/dashboard/faults",
        "/api/v1/dashboard/quality-events",
        "/api/v1/dashboard/filter-options",
        "/api/v1/dashboard/runs/{run_id}",
        "/api/v1/dashboard/export",
    }

    paths = app.openapi()["paths"]
    actual = {path for path in paths if "get" in paths[path]}

    assert expected <= actual


# ==========================================================
# SUMMARY
# ==========================================================


def test_summary_response_shape(monkeypatch):
    fake_summary = {
        "total_runs": 3,
        "expected_pallets": 100.0,
        "actual_pallets": 80.0,
        "expected_tonnes": 40.0,
        "actual_tonnes": 32.0,
        "output_gap_pallets": 20.0,
        "output_gap_tonnes": 8.0,
        "target_achievement_percent": 80.0,
        "planned_downtime_minutes": 45.0,
        "unplanned_downtime_minutes": 30.0,
        "unplanned_downtime_includes_active_faults": True,
        "estimated_lost_packs": 500.0,
        "estimated_lost_minutes": 25.0,
        "estimated_lost_pallets": 2.5,
        "estimated_lost_tonnes": 1.25,
        "open_faults": 1,
        "resolved_faults": 4,
        "machine_setup_minutes": None,
        "machine_repair_minutes": None,
        "machine_classification_status": "not_captured",
    }
    monkeypatch.setattr(
        dashboard_api, "get_dashboard_summary", lambda filters: fake_summary
    )

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == fake_summary


def test_summary_target_achievement_null_when_expected_is_zero(monkeypatch):
    fake_summary = {
        "total_runs": 0,
        "expected_pallets": 0.0,
        "actual_pallets": 0.0,
        "expected_tonnes": 0.0,
        "actual_tonnes": 0.0,
        "output_gap_pallets": 0.0,
        "output_gap_tonnes": 0.0,
        "target_achievement_percent": None,
        "planned_downtime_minutes": 0.0,
        "unplanned_downtime_minutes": 0.0,
        "unplanned_downtime_includes_active_faults": False,
        "estimated_lost_packs": 0.0,
        "estimated_lost_minutes": 0.0,
        "estimated_lost_pallets": 0.0,
        "estimated_lost_tonnes": 0.0,
        "open_faults": 0,
        "resolved_faults": 0,
        "machine_setup_minutes": None,
        "machine_repair_minutes": None,
        "machine_classification_status": "not_captured",
    }
    monkeypatch.setattr(
        dashboard_api, "get_dashboard_summary", lambda filters: fake_summary
    )

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["target_achievement_percent"] is None


# ==========================================================
# RUNS: FILTERING AND PAGINATION
# ==========================================================


def test_runs_filtering_and_pagination(monkeypatch):
    captured = {}

    def fake_list(filters, limit, offset):
        captured["filters"] = filters
        captured["limit"] = limit
        captured["offset"] = offset
        row = {
            "run_id": 1,
            "production_line": "Rovema",
            "line_technician": "Marina",
            "shift": "Night",
            "customer": "Asda",
            "product": "Basmati",
            "pack_type": "Pillow",
            "status": "Active",
            "started_at": _dt(),
            "finished_at": None,
            "pallets_remaining": 10,
            "total_pallets_completed": 5,
            "changeover_type": None,
        }
        return [row], 1

    monkeypatch.setattr(dashboard_api, "list_dashboard_runs", fake_list)

    response = client.get(
        "/api/v1/dashboard/runs",
        params={"production_line": "Rovema", "page": 2, "page_size": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 2
    assert body["page_size"] == 10
    assert body["items"][0]["production_line"] == "Rovema"

    assert captured["filters"]["production_line"] == "Rovema"
    assert captured["limit"] == 10
    assert captured["offset"] == 10  # (page 2 - 1) * page_size 10


def test_runs_page_size_is_capped_at_maximum(monkeypatch):
    monkeypatch.setattr(
        dashboard_api, "list_dashboard_runs", lambda filters, limit, offset: ([], 0)
    )

    response = client.get(
        "/api/v1/dashboard/runs",
        params={"page_size": dashboard_api.MAX_PAGE_SIZE + 1000},
    )

    assert response.status_code == 422


# ==========================================================
# RUN DETAIL
# ==========================================================


def test_run_detail_success(monkeypatch):
    fake_run = {
        "run_id": 42,
        "production_line": "GIC",
        "line_technician": "Bupreet",
        "shift": "Day",
        "customer": "Tesco",
        "product": "Rice",
        "pack_weight_kg": 1.0,
        "packs_per_case": 8,
        "pack_type": "Pillow",
        "target_speed_ppm": 120.0,
        "cases_per_pallet": 220,
        "starting_pallets_remaining": 38,
        "pallets_remaining": 38,
        "previous_run_completed": 0,
        "total_pallets_completed": 0,
        "potential_overrun_pallets": 0,
        "confirmed_overrun_pallets": 0,
        "status": "Active",
        "started_at": _dt(),
        "finished_at": None,
        "changeover_type": None,
    }
    monkeypatch.setattr(
        dashboard_api, "get_dashboard_run", lambda run_id: fake_run
    )

    response = client.get("/api/v1/dashboard/runs/42")

    assert response.status_code == 200
    assert response.json()["run_id"] == 42
    assert response.json()["production_line"] == "GIC"


def test_run_detail_unknown_run_returns_404(monkeypatch):
    monkeypatch.setattr(dashboard_api, "get_dashboard_run", lambda run_id: None)

    response = client.get("/api/v1/dashboard/runs/999999")

    assert response.status_code == 404


# ==========================================================
# DATABASE ERROR -> 503, NO INTERNAL DETAILS LEAKED
# ==========================================================


def test_database_error_returns_503_without_leaking_details(monkeypatch, capsys):
    def fake_summary(filters):
        raise RuntimeError(
            "connection to postgresql://pulse_user:s3cr3t@db.internal/pulse failed"
        )

    monkeypatch.setattr(dashboard_api, "get_dashboard_summary", fake_summary)

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 503

    body_text = response.text
    captured = capsys.readouterr()

    for forbidden in ("s3cr3t", "postgresql://"):
        assert forbidden not in body_text
        assert forbidden not in captured.out
        assert forbidden not in captured.err


# ==========================================================
# OUTPUT TIMELINE
# ==========================================================


def test_output_timeline_response(monkeypatch):
    fake_rows = [
        {
            "hourly_update_id": 1,
            "production_run_id": 10,
            "production_line": "Rovema",
            "pack_weight_kg": 1.0,
            "packs_per_case": 8,
            "cases_per_pallet": 10,
            "expected_pallets": 5.0,
            "actual_pallets": 4.0,
            "sequence_in_run": 1,
        }
    ]
    monkeypatch.setattr(
        dashboard_api, "get_dashboard_output_timeline", lambda filters: fake_rows
    )

    response = client.get("/api/v1/dashboard/output-timeline")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["expected_tonnes"] == pytest.approx(5.0 * 8 * 10 * 1.0 / 1000)
    assert item["actual_tonnes"] == pytest.approx(4.0 * 8 * 10 * 1.0 / 1000)
    assert item["output_gap_pallets"] == pytest.approx(1.0)
    assert item["target_achievement_percent"] == pytest.approx(80.0)
    assert "sequence_in_run" in item
    assert "no timestamp column" in response.json()["note"]


# ==========================================================
# PLANNED DOWNTIME
# ==========================================================


def test_planned_downtime_response(monkeypatch):
    fake_rows = [
        {"downtime_type": "Film Change", "total_minutes": 30, "occurrences": 2},
        {"downtime_type": "None", "total_minutes": 0, "occurrences": 5},
    ]
    monkeypatch.setattr(
        dashboard_api, "get_dashboard_planned_downtime", lambda filters: fake_rows
    )

    response = client.get("/api/v1/dashboard/planned-downtime")

    assert response.status_code == 200
    body = response.json()
    assert body["total_minutes"] == 30
    assert {g["downtime_type"] for g in body["groups"]} == {"Film Change", "None"}


# ==========================================================
# ENGINEERING DOWNTIME - HONEST ABOUT UNSUPPORTED CLASSIFICATION
# ==========================================================


def test_engineering_downtime_reports_unsupported_classification_honestly(
    monkeypatch,
):
    fake_downtime_rows = [
        {
            "downtime_event_id": 1,
            "production_run_id": 10,
            "production_line": "Rovema",
            "fault_id": 1,
            "machine": "Casepacker",
            "reason": "Jam",
            "reported_by": "Marina",
            "engineer_called": True,
            "production_status": "Ongoing",
            "engineering_status": "Ongoing",
            "engineer": "Aaron",
            "retrospective": False,
            "opened_at": _dt(),
            "resolved_at": None,
        },
        {
            "downtime_event_id": 2,
            "production_run_id": 10,
            "production_line": "Rovema",
            "fault_id": 2,
            "machine": "Conveyor",
            "reason": "Stop",
            "reported_by": "Marina",
            "engineer_called": False,
            "production_status": "Resolved",
            "engineering_status": "Not Started",
            "engineer": None,
            "retrospective": False,
            "opened_at": _dt(8),
            "resolved_at": _dt(9),
        },
    ]
    fake_engineering_rows = [
        {"update_type": "Investigation"},
        {"update_type": "Investigation"},
        {"update_type": "Resolution"},
    ]

    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_downtime_events",
        lambda filters: fake_downtime_rows,
    )
    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_engineering_updates",
        lambda filters: fake_engineering_rows,
    )

    response = client.get("/api/v1/dashboard/engineering-downtime")

    assert response.status_code == 200
    body = response.json()

    assert body["machine_setup_minutes"] is None
    assert body["machine_repair_minutes"] is None
    assert body["machine_classification_status"] == "not_captured"
    assert body["total_faults"] == 2
    assert body["engineer_called_faults"] == 1
    assert body["open_faults"] == 1
    assert body["resolved_faults"] == 1
    assert body["unplanned_downtime_includes_active_faults"] is True

    breakdown = {
        entry["engineering_class"]: entry["count"]
        for entry in body["update_type_breakdown"]
    }
    assert breakdown == {"Investigation": 2, "Resolution": 1}


# ==========================================================
# FAULTS
# ==========================================================


def test_faults_response(monkeypatch):
    fake_rows = [
        {
            "downtime_event_id": 1,
            "production_run_id": 10,
            "production_line": "Rovema",
            "fault_id": 1,
            "machine": "Casepacker",
            "reason": "Jam",
            "reported_by": "Marina",
            "engineer_called": True,
            "production_status": "Ongoing",
            "engineering_status": "Ongoing",
            "engineer": "Aaron",
            "retrospective": False,
            "opened_at": _dt(),
            "resolved_at": None,
            "duration_minutes": 42.5,
            "duration_is_active": True,
        }
    ]
    monkeypatch.setattr(dashboard_api, "get_dashboard_faults", lambda filters: fake_rows)

    response = client.get("/api/v1/dashboard/faults")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["duration_is_active"] is True
    assert body["items"][0]["duration_minutes"] == 42.5


# ==========================================================
# QUALITY EVENTS - REPORTS UNAVAILABLE DATA
# ==========================================================


def test_quality_events_reports_unavailable_data():
    response = client.get("/api/v1/dashboard/quality-events")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["data_status"] == "not_available"
    assert "not captured" in body["message"]


# ==========================================================
# CSV EXPORT
# ==========================================================


def test_export_returns_csv_with_correct_content_type(monkeypatch):
    fake_rows = [
        {
            "run_id": 1,
            "production_line": "Rovema",
            "line_technician": "Marina",
            "shift": "Night",
            "customer": "Asda",
            "product": "Basmati",
            "pack_type": "Pillow",
            "status": "Completed",
            "started_at": _dt(),
            "finished_at": _dt(10),
            "pallets_remaining": 0,
            "total_pallets_completed": 38,
            "changeover_type": "Customer Changeover",
        }
    ]
    monkeypatch.setattr(
        dashboard_api,
        "list_dashboard_runs",
        lambda filters, limit, offset: (fake_rows, 1),
    )

    response = client.get("/api/v1/dashboard/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    body_text = response.text
    assert "run_id" in body_text.splitlines()[0]
    assert "Rovema" in body_text
    assert "Marina" in body_text


# ==========================================================
# TEST-DATA EXCLUSION IS CENTRALISED AND ALWAYS APPLIED
# ==========================================================


def test_test_data_exclusion_clause_is_always_first_condition():
    for builder in (
        database._run_conditions,
        database._fault_conditions,
        database._engineering_conditions,
    ):
        conditions, _params = builder({})
        assert conditions[0] == database._TEST_DATA_EXCLUSION_SQL


def test_test_data_exclusion_clause_covers_all_four_required_fields():
    clause = database._TEST_DATA_EXCLUSION_SQL
    assert "production_line NOT ILIKE 'TEST-%'" in clause
    assert "customer NOT ILIKE '%TEST-%'" in clause
    assert "product NOT ILIKE '%TEST-%'" in clause
    assert "shift NOT ILIKE '%TEST-%'" in clause


# ==========================================================
# CORS
# ==========================================================


def test_cors_allows_hmi_origin():
    response = client.get(
        "/api/v1/dashboard/quality-events", headers={"Origin": HMI_ORIGIN}
    )
    assert response.headers["access-control-allow-origin"] == HMI_ORIGIN


def test_cors_allows_dashboard_origin():
    response = client.get(
        "/api/v1/dashboard/quality-events", headers={"Origin": DASHBOARD_ORIGIN}
    )
    assert response.headers["access-control-allow-origin"] == DASHBOARD_ORIGIN


def test_cors_rejects_other_origins():
    response = client.options(
        "/api/v1/dashboard/quality-events",
        headers={
            "Origin": "https://some-other-site.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_cors_never_configures_a_wildcard_origin():
    from src.api import app as api_app

    for middleware in api_app.user_middleware:
        options = getattr(middleware, "kwargs", {})
        allow_origins = options.get("allow_origins")
        if allow_origins is not None:
            assert "*" not in allow_origins
