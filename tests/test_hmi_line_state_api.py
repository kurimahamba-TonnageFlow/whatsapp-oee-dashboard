"""
Offline HTTP tests for GET /api/v1/hmi/lines (src/hmi_config_api.py),
the authoritative cross-device line state the Home screen polls.

Never touches Supabase: src.hmi_config_api.get_hmi_line_state is
monkeypatched at the point the module imported it, and the clock is
fixed so "stale" is deterministic.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import hmi_config_api
from src import pulse_calculations as calc
from src.api import app


client = TestClient(app)

NOW = datetime(2026, 1, 12, 9, 0, tzinfo=timezone.utc)
SECRET = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(hmi_config_api, "_now", lambda: NOW)


@pytest.fixture
def lines(monkeypatch):
    def install(rows):
        monkeypatch.setattr(hmi_config_api, "get_hmi_line_state", lambda: rows)

    return install


def active_line(**overrides):
    row = {
        "line_id": 1,
        "line_name": "Rovema",
        "run_id": 4101,
        "line_technician": "Liam",
        "shift": "Night",
        "customer": "Asda",
        "product": "Basmati",
        "started_at": NOW - timedelta(minutes=90),
        "last_hourly_update_at": NOW - timedelta(minutes=20),
        "open_planned_downtime_id": None,
        "last_planned_downtime_at": None,
        "open_changeover_id": None,
        "last_changeover_at": None,
        "open_fault_count": 0,
        "last_fault_opened_at": None,
    }
    row.update(overrides)
    return row


def available_line(line_id=2, name="GIC"):
    return {
        "line_id": line_id,
        "line_name": name,
        "run_id": None,
        "line_technician": None,
        "shift": None,
        "customer": None,
        "product": None,
        "started_at": None,
        "last_hourly_update_at": None,
        "open_planned_downtime_id": None,
        "last_planned_downtime_at": None,
        "open_changeover_id": None,
        "last_changeover_at": None,
        "open_fault_count": 0,
        "last_fault_opened_at": None,
    }


def get_lines():
    response = client.get("/api/v1/hmi/lines")
    assert response.status_code == 200
    return response.json()


def line_named(body, name):
    return next(line for line in body["lines"] if line["production_line"] == name)


# ==========================================================
# EVERY CONFIGURED LINE
# ==========================================================


def test_returns_every_active_configured_line(lines):
    lines([active_line(), available_line(2, "GIC"), available_line(3, "Guill")])

    body = get_lines()

    assert [line["production_line"] for line in body["lines"]] == ["Rovema", "GIC", "Guill"]
    assert [line["line_id"] for line in body["lines"]] == [1, 2, 3]


def test_inactive_configured_lines_are_excluded(lines):
    """A line switched off in Management is not offered to operators at
    all - the query filters on pl.active, so it is simply not among the
    rows the endpoint serialises."""
    lines([active_line(), available_line(2, "GIC")])

    body = get_lines()

    assert "Guill" not in [line["production_line"] for line in body["lines"]]


def test_reports_the_stale_threshold_it_used(lines):
    lines([available_line()])

    assert get_lines()["stale_after_minutes"] == calc.DEFAULT_STALE_AFTER_MINUTES


# ==========================================================
# ACTIVE VS AVAILABLE
# ==========================================================


def test_an_active_line_reports_the_run_and_who_is_on_it(lines):
    lines([active_line()])

    line = line_named(get_lines(), "Rovema")

    assert line["has_active_run"] is True
    assert line["run_id"] == 4101
    assert line["line_technician"] == "Liam"
    assert line["shift"] == "Night"
    assert line["customer"] == "Asda"
    assert line["product"] == "Basmati"
    assert line["started_at"].startswith("2026-01-12T07:30:00")


def test_an_available_line_reports_no_run_rather_than_missing_data(lines):
    lines([available_line()])

    line = line_named(get_lines(), "GIC")

    assert line["has_active_run"] is False
    assert line["run_id"] is None
    assert line["line_technician"] is None
    assert line["started_at"] is None
    assert line["planned_downtime_active"] is False
    assert line["changeover_active"] is False
    assert line["engineering_fault_open"] is False
    assert line["stale_status"] == "no_active_run"


def test_two_devices_polling_see_the_same_active_run(lines):
    lines([active_line()])

    first = TestClient(app).get("/api/v1/hmi/lines").json()
    second = TestClient(app).get("/api/v1/hmi/lines").json()

    assert line_named(first, "Rovema")["run_id"] == line_named(second, "Rovema")["run_id"] == 4101
    assert line_named(first, "Rovema")["has_active_run"] is True
    assert line_named(second, "Rovema")["has_active_run"] is True


# ==========================================================
# WHAT IS HAPPENING ON AN ACTIVE LINE
# ==========================================================


def test_open_planned_downtime_is_reported(lines):
    lines([active_line(
        open_planned_downtime_id=77,
        last_planned_downtime_at=NOW - timedelta(minutes=5),
    )])

    line = line_named(get_lines(), "Rovema")

    assert line["planned_downtime_active"] is True
    assert line["changeover_active"] is False


def test_open_changeover_is_reported(lines):
    lines([active_line(open_changeover_id=12, last_changeover_at=NOW - timedelta(minutes=8))])

    line = line_named(get_lines(), "Rovema")

    assert line["changeover_active"] is True


def test_open_engineering_fault_is_reported(lines):
    lines([active_line(open_fault_count=2, last_fault_opened_at=NOW - timedelta(minutes=3))])

    line = line_named(get_lines(), "Rovema")

    assert line["engineering_fault_open"] is True
    assert line["open_fault_count"] == 2


def test_no_open_fault_is_reported_honestly_as_none(lines):
    lines([active_line(open_fault_count=0)])

    line = line_named(get_lines(), "Rovema")

    assert line["engineering_fault_open"] is False
    assert line["open_fault_count"] == 0


# ==========================================================
# FRESHNESS
# ==========================================================


def test_a_recently_updated_run_is_current(lines):
    lines([active_line(last_hourly_update_at=NOW - timedelta(minutes=20))])

    line = line_named(get_lines(), "Rovema")

    assert line["stale_status"] == "current"
    assert line["minutes_since_last_hourly_update"] == 20


def test_a_run_with_no_recent_update_is_stale(lines):
    lines([active_line(last_hourly_update_at=NOW - timedelta(minutes=120))])

    line = line_named(get_lines(), "Rovema")

    assert line["stale_status"] == "stale"
    assert line["minutes_since_last_hourly_update"] == 120
    assert "120" in line["stale_reason"]


def test_a_run_with_no_hourly_update_yet_is_measured_from_its_start(lines):
    lines([active_line(started_at=NOW - timedelta(minutes=200), last_hourly_update_at=None)])

    line = line_named(get_lines(), "Rovema")

    assert line["stale_status"] == "stale"
    assert line["minutes_since_last_hourly_update"] is None
    assert "since the run started" in line["stale_reason"]


def test_latest_activity_is_the_most_recent_recorded_event(lines):
    lines([active_line(
        started_at=NOW - timedelta(minutes=300),
        last_hourly_update_at=NOW - timedelta(minutes=90),
        last_fault_opened_at=NOW - timedelta(minutes=4),
    )])

    line = line_named(get_lines(), "Rovema")

    assert line["last_activity_at"].startswith("2026-01-12T08:56:00")


def test_legacy_rows_without_timestamps_do_not_invent_an_activity_time(lines):
    """A run whose hourly updates predate created_at contributes no
    timestamp - the run start is used, and nothing is guessed."""
    lines([active_line(last_hourly_update_at=None, started_at=NOW - timedelta(minutes=30))])

    line = line_named(get_lines(), "Rovema")

    assert line["last_activity_at"].startswith("2026-01-12T08:30:00")
    assert line["minutes_since_last_hourly_update"] is None


# ==========================================================
# SAFETY
# ==========================================================


@pytest.mark.parametrize(
    "management_only",
    [
        "tonnes", "tonnage", "oee", "achievement", "target", "waste",
        "cost", "xray", "performance", "pallets_remaining",
    ],
)
def test_no_management_only_information_is_exposed(lines, management_only):
    lines([active_line(), available_line()])

    assert management_only not in client.get("/api/v1/hmi/lines").text.lower()


def test_backend_unavailable_is_a_safe_503_with_no_secrets(monkeypatch, capsys):
    def explode():
        raise RuntimeError(f"connection to {SECRET} failed")

    monkeypatch.setattr(hmi_config_api, "get_hmi_line_state", explode)

    response = client.get("/api/v1/hmi/lines")

    assert response.status_code == 503
    assert response.json()["detail"] == "Could not load line status. Please try again."
    assert SECRET not in response.text
    captured = capsys.readouterr()
    assert "s3cr3t" not in captured.out + captured.err


def test_the_endpoint_needs_no_authentication_and_writes_nothing(lines):
    """The factory-floor HMI has no login, so a GET must never be the
    thing that creates or changes a run."""
    lines([active_line()])

    assert client.get("/api/v1/hmi/lines").status_code == 200
    # No write method is routed here at all.
    assert client.post("/api/v1/hmi/lines").status_code in (404, 405)
    assert client.patch("/api/v1/hmi/lines").status_code in (404, 405)
