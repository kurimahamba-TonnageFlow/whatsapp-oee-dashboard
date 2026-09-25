"""
Offline tests for the protected, window-based management dashboard:
the pure report builders in src/dashboard_reports.py and the Stage 6B1
routes in src/dashboard_api.py.

A synthetic Day shift (Monday 12 January 2026, GMT) is used throughout,
with every expected figure worked out by hand in the comments. HTTP
tests monkeypatch every src.database function dashboard_api imported;
no Supabase connection is ever opened.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import dashboard_api, dashboard_reports, engineering_auth, management_auth
from src.api import DASHBOARD_ORIGIN, app
from src.factory_time import current_shift_window, factory_day_start, rolling_24h_window, week_window_starting


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


NOW = utc(2026, 1, 12, 9, 30)  # Day shift, 06:00-14:00 GMT
SHIFT = current_shift_window(NOW)
SECRET = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


def run(run_id, line, speed, ppc, cpp, weight="1.000", status="Active"):
    return {
        "id": run_id, "production_line": line, "line_technician": "Liam", "shift": "Day",
        "customer": "Asda", "product": "Basmati", "format": "Pillow",
        "pack_weight_kg": Decimal(weight), "packs_per_case": ppc, "cases_per_pallet": cpp,
        "target_speed_ppm": Decimal(speed), "status": status, "started_at": utc(2026, 1, 12, 6),
        "finished_at": None, "pallets_remaining": Decimal("13.21"), "total_pallets_completed": Decimal("10.79"),
    }


def hourly(row_id, run_id, start_hour, expected, pallets, reason=None):
    return {
        "id": row_id, "production_run_id": run_id, "expected_packs": Decimal(expected),
        "actual_pallets": Decimal(pallets), "period_started_at": utc(2026, 1, 12, start_hour),
        "period_ended_at": utc(2026, 1, 12, start_hour + 1), "created_at": utc(2026, 1, 12, start_hour + 1),
        "other_loss_reason": reason, "unexplained_loss_reason": None,
    }


def fault(fault_id, machine, opened, resolved, preventable=None, classification=None):
    return {
        "id": fault_id, "production_run_id": 1, "production_line": "Rovema", "fault_id": fault_id,
        "machine": machine, "machine_id": None, "reason": "Jam",
        "production_status": "Ongoing" if resolved is None else "Resolved",
        "engineering_status": "Not Started", "engineer": None, "opened_at": opened,
        "resolved_at": resolved, "maintenance_preventable": preventable,
        "repair_classification": classification,
    }


def window_data(xray=()):
    # Rovema run 1: 8.4 ppm, 10 x 10 = 100 packs/pallet, 1 kg.
    #   3 periods x 504 expected = 1512 packs; actual 375 + 504 + 200 = 1079 -> gap 433.
    #   Planned 06:10-06:20 (10 min = 84 packs); BV1 fault 06:30-06:40 (10 min = 84 packs).
    #   Casepacker fault opened 09:10, still open - outside the reported periods.
    # GIC run 2: 120 ppm, 8 x 220 = 1760 packs/pallet; 7200 expected, 4 pallets = 7040 actual (97.8%).
    # Guill: no run.
    return {
        "lines": ["Rovema", "GIC", "Guill"],
        "runs": [run(1, "Rovema", "8.4", 10, 10), run(2, "GIC", "120", 8, 220)],
        "hourly": [
            hourly(11, 1, 6, 504, "3.75"),
            hourly(12, 1, 7, 504, "5.04"),
            hourly(13, 1, 8, 504, "2", reason="Film slow"),
            hourly(21, 2, 6, 7200, "4"),
        ],
        "legacy_hourly_without_timestamp": 3,
        "planned": [{"id": 1, "production_run_id": 1, "reason": "Film Change",
                     "started_at": utc(2026, 1, 12, 6, 10), "ended_at": utc(2026, 1, 12, 6, 20)}],
        "faults": [
            fault(31, "BV1", utc(2026, 1, 12, 6, 30), utc(2026, 1, 12, 6, 40), "Yes", "Mechanical"),
            fault(32, "Casepacker", utc(2026, 1, 12, 9, 10), None),
        ],
        "xray": list(xray),
        "latest_activity": {"Rovema": utc(2026, 1, 12, 9, 10), "GIC": utc(2026, 1, 12, 7)},
        "last_hourly": {"Rovema": utc(2026, 1, 12, 9), "GIC": utc(2026, 1, 12, 7)},
    }


def lines_by_name(report):
    return {line["production_line"]: line for line in report["lines"]}


# ==========================================================
# ACTIVE (UNCLOSED) DOWNTIME IN ATTRIBUTION
# ==========================================================


def test_a_still_open_planned_stop_is_attributed_not_treated_as_zero_length():
    """An event with no ended_at is still costing the line minutes. Its
    end is set to the current server time before attribution, so it is
    attributed across the reported periods it overlaps - not skipped as a
    zero-length interval."""
    data = window_data()
    data["planned"] = [{
        "id": 1, "production_run_id": 1, "reason": "Film Change",
        "started_at": utc(2026, 1, 12, 8, 30), "ended_at": None,
    }]

    attribution = dashboard_reports.build_overview(data, SHIFT, NOW)["gap_attribution"]

    # Open at 08:30, extended to NOW (09:30), then clipped to the
    # reported periods (06:00-09:00): 08:30 -> 09:00 = 30 minutes.
    assert attribution["planned_downtime"]["minutes"] == 30.0


def test_an_open_interval_is_bounded_and_never_runs_away_with_the_clock():
    """The later the report is run, the more an open event would grow if
    it were unbounded. It is clipped to the window and to the periods
    actually reported, so it stays bounded."""
    data = window_data()
    data["planned"] = [{
        "id": 1, "production_run_id": 1, "reason": "Film Change",
        "started_at": utc(2026, 1, 12, 8, 30), "ended_at": None,
    }]

    at_0930 = dashboard_reports.build_overview(data, SHIFT, NOW)["gap_attribution"]
    much_later = dashboard_reports.build_overview(data, SHIFT, utc(2026, 1, 12, 15))["gap_attribution"]

    # Both bounded by the reported coverage ending at 09:00.
    assert at_0930["planned_downtime"]["minutes"] == 30.0
    assert much_later["planned_downtime"]["minutes"] == 30.0


def test_downtime_beyond_the_last_reported_period_is_not_attributed_yet():
    """Gap attribution explains the gap between expected and actual
    output for periods that were actually reported. A stop after the last
    hourly update has no measured gap to explain yet, so attributing it
    would invent loss against unmeasured output."""
    data = window_data()
    data["planned"] = [{
        "id": 1, "production_run_id": 1, "reason": "Film Change",
        "started_at": utc(2026, 1, 12, 9, 10), "ended_at": None,
    }]

    attribution = dashboard_reports.build_overview(data, SHIFT, NOW)["gap_attribution"]

    assert attribution["planned_downtime"]["minutes"] == 0.0


def test_completed_and_active_downtime_combine_without_double_counting():
    data = window_data()
    data["planned"] = [
        {"id": 1, "production_run_id": 1, "reason": "Film Change",
         "started_at": utc(2026, 1, 12, 6, 10), "ended_at": utc(2026, 1, 12, 6, 25)},
        {"id": 2, "production_run_id": 1, "reason": "CCP Check",
         "started_at": utc(2026, 1, 12, 6, 20), "ended_at": None},
    ]

    attribution = dashboard_reports.build_overview(data, SHIFT, NOW)["gap_attribution"]

    # 06:10 -> 09:00 (coverage end) merged = 170 minutes, not 15 + 160.
    assert attribution["planned_downtime"]["minutes"] == 170.0


# ==========================================================
# LEGACY DATA DISCLOSURE
# ==========================================================


def test_excluded_legacy_records_are_reported_with_a_plain_message():
    quality = dashboard_reports.build_overview(window_data(), SHIFT, NOW)["data_quality"]

    assert quality["legacy_records_excluded"] is True
    assert quality["legacy_record_count"] == 3
    # Plain language: what is missing, why, and that the total reads low.
    assert "3 older hourly updates" in quality["message"]
    assert "lower than what was actually produced" in quality["message"]
    assert "no period times have been estimated" in quality["message"].lower()
    # created_at exists live, so the message must not claim otherwise.
    assert "they have a submission timestamp" in quality["message"].lower()
    assert "captured period start and period end" in quality["message"]


def test_no_legacy_records_reports_no_warning_rather_than_a_vague_one():
    data = window_data()
    data["legacy_hourly_without_timestamp"] = 0

    quality = dashboard_reports.build_overview(data, SHIFT, NOW)["data_quality"]

    assert quality["legacy_records_excluded"] is False
    assert quality["legacy_record_count"] == 0
    assert quality["message"] is None


def test_a_single_excluded_record_is_described_in_the_singular():
    data = window_data()
    data["legacy_hourly_without_timestamp"] = 1

    message = dashboard_reports.build_overview(data, SHIFT, NOW)["data_quality"]["message"]

    assert "1 older hourly update could not be included" in message


def test_a_missing_legacy_count_is_treated_as_none_excluded():
    data = window_data()
    del data["legacy_hourly_without_timestamp"]

    assert dashboard_reports.legacy_data_quality(data) == {
        "legacy_records_excluded": False,
        "legacy_record_count": 0,
        "message": None,
    }


@pytest.mark.parametrize(
    "builder",
    [
        lambda data: dashboard_reports.build_overview(data, SHIFT, NOW),
        lambda data: dashboard_reports.build_gap_attribution(data, SHIFT, NOW),
        lambda data: dashboard_reports.build_machine_summary(data, SHIFT, NOW),
        lambda data: dashboard_reports.build_engineering_classification(data, SHIFT, NOW),
        lambda data: dashboard_reports.build_xray_waste(data, SHIFT, NOW),
        lambda data: dashboard_reports.build_weekly_targets(
            [], data, week_window_starting(date(2026, 1, 12)), NOW
        ),
    ],
    ids=["overview", "gap", "machines", "engineering", "xray", "weekly"],
)
def test_no_report_presents_a_total_without_the_exclusion_warning(builder):
    """A window total that silently omits legacy rows would read as a
    genuine production drop. Every report carrying a total carries the
    disclosure with it."""
    report = builder(window_data())

    assert report["data_quality"]["legacy_records_excluded"] is True
    assert report["data_quality"]["legacy_record_count"] == 3
    assert report["data_quality"]["message"]


def test_the_disclosure_states_that_no_period_times_were_invented():
    message = dashboard_reports.legacy_data_quality(window_data())["message"]

    assert "no period times have been estimated" in message.lower()
    assert "unchanged" in message.lower()
    # It must not imply the submission timestamp is missing - it is not.
    assert "no timestamp" not in message.lower()


# ==========================================================
# OVERVIEW BUILDER
# ==========================================================


def test_overview_site_output_and_line_attention():
    report = dashboard_reports.build_overview(window_data(), SHIFT, NOW)
    lines = lines_by_name(report)

    assert report["window"]["kind"] == "current_shift"
    assert report["output"]["hourly_update_count"] == 4
    assert report["open_faults"] == 1
    assert report["legacy_hourly_updates_without_timestamp"] == 3

    assert lines["Rovema"]["attention_status"] == "red"
    assert "1 open fault" in lines["Rovema"]["attention_explanation"]
    assert lines["Rovema"]["output"]["output_gap_packs"] == 433.0
    assert lines["Rovema"]["output"]["production_achievement_percent"] == 71.4

    assert lines["GIC"]["attention_status"] == "green"
    assert lines["GIC"]["output"]["production_achievement_percent"] == 97.8

    assert lines["Guill"]["attention_status"] == "grey"
    assert lines["Guill"]["active_run"] is None


def test_overview_freshness_marks_stale_lines():
    report = dashboard_reports.build_overview(window_data(), SHIFT, NOW)
    lines = lines_by_name(report)

    assert lines["Rovema"]["freshness"]["stale_status"] == "current"
    assert lines["Rovema"]["freshness"]["minutes_since_last_hourly_update"] == 30.0
    assert lines["GIC"]["freshness"]["stale_status"] == "stale"
    assert lines["Guill"]["freshness"]["stale_status"] == "no_active_run"

    assert report["freshness"]["stale_status"] == "stale"
    assert report["freshness"]["stale_lines"] == ["GIC"]
    assert report["freshness"]["latest_activity_at"] == utc(2026, 1, 12, 9, 10)
    assert report["freshness"]["last_hourly_update_at"] == utc(2026, 1, 12, 9)
    assert report["generated_at"] == NOW


def test_overview_gap_attribution_is_estimated_capped_and_complete():
    attribution = dashboard_reports.build_overview(window_data(), SHIFT, NOW)["gap_attribution"]

    assert attribution["calculation_status"] == "estimated"
    assert attribution["planned_downtime"]["minutes"] == 10.0
    assert attribution["planned_downtime"]["estimated_lost_packs"] == 84.0
    assert attribution["unplanned_downtime"]["minutes"] == 10.0
    assert attribution["unplanned_downtime"]["estimated_lost_tonnes"] == 0.084
    # Rovema: remainder 433 - 168 = 265 is fully explained by the 304-pack
    # shortfall in the hour with a recorded reason. GIC: 7200 - 7040 =
    # 160 packs short with no downtime and no reason -> unexplained.
    assert attribution["other_or_speed_loss"]["estimated_lost_packs"] == 265.0
    assert attribution["unexplained_gap"]["estimated_lost_packs"] == 160.0
    assert attribution["measured_output_gap"]["estimated_lost_packs"] == 593.0
    assert attribution["by_machine"] == [
        {"production_line": "Rovema", "machine": "BV1", "minutes": 10.0,
         "estimated_lost_packs": 84.0, "estimated_lost_pallets": 0.84, "estimated_lost_tonnes": 0.084},
    ]


def test_overview_estimated_oee_is_partial_without_xray_counts():
    oee = dashboard_reports.build_overview(window_data(), SHIFT, NOW)["estimated_oee"]

    # Coverage 180 + 60 = 240 min; planned 10, unplanned 10 -> 230 planned production, 220 run.
    assert oee["availability_percent"] == 95.7
    # Effective minutes 1079/8.4 + 7040/120 = 187.12 over 220 run minutes.
    assert oee["performance_percent"] == 85.1
    assert oee["estimated_quality_percent"] is None
    assert oee["estimated_oee_percent"] is None
    assert oee["calculation_status"] == "partial"


def test_overview_estimated_oee_uses_usable_xray_counts():
    xray = [{"id": 1, "production_run_id": 1, "production_line": "Rovema", "capture_point": "shift_end",
             "shift": "Day", "count_available": True, "xray_pack_count": 1100, "unavailable_reason": None,
             "palletised_packs": Decimal(1079), "post_xray_pack_difference": Decimal(21),
             "estimated_waste_percent": Decimal("1.9"), "waste_status": "estimated",
             "captured_at": utc(2026, 1, 12, 9, 20)}]
    lines = lines_by_name(dashboard_reports.build_overview(window_data(xray), SHIFT, NOW))

    assert lines["Rovema"]["estimated_oee"]["calculation_status"] == "estimated"
    assert lines["Rovema"]["estimated_oee"]["estimated_quality_percent"] == 98.1
    assert lines["GIC"]["estimated_oee"]["calculation_status"] == "partial"


def test_invalid_pack_configuration_is_reported_not_silently_used():
    data = window_data()
    data["runs"][1]["target_speed_ppm"] = Decimal(0)

    report = dashboard_reports.build_overview(data, SHIFT, NOW)

    assert any("Run 2" in issue for issue in report["data_issues"])
    assert lines_by_name(report)["GIC"]["output"]["hourly_update_count"] == 0


# ==========================================================
# OTHER BUILDERS
# ==========================================================


def test_machine_summary_ranks_by_estimated_tonnes_and_keeps_oee_line_level():
    report = dashboard_reports.build_machine_summary(window_data(), SHIFT, NOW)
    machines = report["machines"]

    assert [m["machine"] for m in machines] == ["BV1", "Casepacker"]
    assert machines[0]["estimated_lost_tonnes"] == 0.084
    assert machines[0]["maintenance_preventable"]["Yes"] == 1
    assert machines[1]["open_faults"] == 1
    assert machines[1]["downtime_minutes_in_window"] == 20.0
    assert all(m["machine_oee"] is None for m in machines)
    assert "per-machine output" in machines[0]["machine_oee_unavailable_reason"]


def test_engineering_classification_distinguishes_setting_physical_and_preventability():
    report = dashboard_reports.build_engineering_classification(window_data(), SHIFT, NOW)

    assert report["by_repair_classification"]["physical_component_failure"]["fault_count"] == 1
    assert report["by_repair_classification"]["machine_setup_or_setting"]["fault_count"] == 0
    assert report["by_repair_classification"]["not_classified"]["fault_count"] == 1
    assert report["by_maintenance_preventable"]["yes"]["fault_count"] == 1
    assert report["by_maintenance_preventable"]["not_recorded"]["fault_count"] == 1
    assert report["by_maintenance_preventable"]["unsure"]["fault_count"] == 0
    assert report["by_status"] == {
        "open": {"fault_count": 1, "downtime_minutes_in_window": 20.0},
        "closed": {"fault_count": 1, "downtime_minutes_in_window": 10.0},
    }


def test_xray_waste_combines_only_usable_captures():
    rows = [
        {"id": 1, "production_run_id": 1, "production_line": "Rovema", "capture_point": "shift_end",
         "shift": "Day", "count_available": True, "xray_pack_count": 1000, "unavailable_reason": None,
         "palletised_packs": Decimal(950), "post_xray_pack_difference": Decimal(50),
         "estimated_waste_percent": Decimal(5), "waste_status": "estimated", "captured_at": NOW},
        {"id": 2, "production_run_id": 2, "production_line": "GIC", "capture_point": "run_completion",
         "shift": "Day", "count_available": False, "xray_pack_count": None, "unavailable_reason": "Offline",
         "palletised_packs": Decimal(700), "post_xray_pack_difference": None,
         "estimated_waste_percent": None, "waste_status": "unavailable", "captured_at": NOW},
    ]
    report = dashboard_reports.build_xray_waste(window_data(rows), SHIFT, NOW)

    assert report["combined_estimate"]["estimated_post_xray_waste_percent"] == 5.0
    assert report["combined_estimate"]["captures_included"] == 1
    assert report["combined_estimate"]["captures_excluded"] == 1
    assert report["captures"][1]["estimated_post_xray_waste_percent"] is None


def test_weekly_targets_use_pace_through_the_week():
    week = week_window_starting(date(2026, 1, 12))
    now = week.start + timedelta(hours=12)  # 12 of 168 hours elapsed
    targets = [
        {"scope": "site", "production_line": None, "target_tonnes": Decimal(100)},
        {"scope": "line", "production_line": "Rovema", "target_tonnes": Decimal(30)},
    ]

    report = dashboard_reports.build_weekly_targets(targets, window_data(), week, now)
    lines = {entry["production_line"]: entry for entry in report["lines"]}

    # Site: 1.079 + 7.04 = 8.119 t actual vs 100 x 12/168 = 7.143 t expected by now.
    assert report["site"]["actual_tonnes"] == 8.119
    assert report["site"]["expected_tonnes_by_now"] == 7.143
    assert report["site"]["target_status"] == "green"
    # Rovema: 1.079 t vs 30 x 12/168 = 2.143 t -> behind pace.
    assert lines["Rovema"]["target_status"] == "red"
    assert lines["GIC"]["target_status"] == "grey"
    assert lines["Guill"]["target_status"] == "grey"
    assert report["week"]["start"] == "2026-01-12T06:00:00+00:00"


def changeover(changeover_id, line, started, minutes, customer="Tesco", technician="Liam"):
    completed = minutes is not None
    return {
        "id": changeover_id, "production_line": line, "line_technician": technician, "shift": "Day",
        "status": "Completed" if completed else "Open", "started_at": started,
        "completed_at": None, "completed_by": None,
        "duration_minutes": Decimal(minutes) if completed else None,
        "previous_production_run_id": None, "previous_customer": "Asda", "previous_product": "Basmati",
        "previous_pack_weight_kg": Decimal("1.000"), "previous_format": "Pillow",
        "new_production_run_id": None, "new_customer": customer if completed else None,
        "new_product": "Jasmine" if completed else None,
        "new_pack_weight_kg": Decimal("4.000") if completed else None,
        "new_format": "Block" if completed else None, "note": None,
    }


CHANGEOVERS = [
    changeover(1, "GIC", utc(2026, 1, 12, 8), "40"),
    changeover(2, "GIC", utc(2026, 1, 13, 5, 30), "20"),   # 05:30 GMT belongs to factory day 12 Jan
    changeover(3, "Rovema", utc(2026, 1, 20, 9), "75", customer="Lidl"),
    changeover(4, "Rovema", utc(2026, 1, 20, 12), None),
]


@pytest.mark.parametrize(
    "group_by, expected",
    [
        ("line", {"GIC": (2, 60.0), "Rovema": (2, 75.0)}),
        ("day", {"2026-01-12": (2, 60.0), "2026-01-20": (2, 75.0)}),
        ("week", {"2026-01-12": (2, 60.0), "2026-01-19": (2, 75.0)}),
        ("month", {"2026-01": (4, 135.0)}),
        ("duration", {"30_to_60_minutes": (1, 40.0), "15_to_30_minutes": (1, 20.0),
                      "60_minutes_or_more": (1, 75.0), "open": (1, 0.0)}),
        ("customer", {"Tesco": (2, 60.0), "Lidl": (1, 75.0), "Asda": (1, 0.0)}),
    ],
)
def test_changeover_grouping(group_by, expected):
    report = dashboard_reports.build_changeover_report(CHANGEOVERS, group_by, NOW)
    actual = {g["key"]: (g["changeover_count"], g["total_duration_minutes"]) for g in report["groups"]}
    assert actual == expected


def test_changeover_report_without_grouping_serialises_rows():
    report = dashboard_reports.build_changeover_report(CHANGEOVERS, None, NOW)
    assert report["groups"] is None
    assert report["changeovers"][0]["changeover_id"] == 1
    assert report["changeovers"][0]["duration_minutes"] == 40.0
    assert "first acceptable packs" in report["definition"]


# ==========================================================
# HTTP: AUTHENTICATION
# ==========================================================

TEST_MANAGEMENT_PIN = "test-management-pin-0000"


@pytest.fixture
def anonymous_client():
    return TestClient(app)


@pytest.fixture
def manager_client(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", TEST_MANAGEMENT_PIN)
    management_auth._sessions.clear()
    token = management_auth.create_session("Test Manager")["token"]
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    yield client
    management_auth._sessions.clear()


@pytest.fixture
def no_database(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Dashboard data must not be read without a valid Management session.")

    for name in dir(dashboard_api):
        if name.startswith(("get_dashboard_", "list_")):
            monkeypatch.setattr(dashboard_api, name, forbidden)


def dashboard_get_paths():
    paths = app.openapi()["paths"]
    return sorted(
        path.replace("{run_id}", "1")
        for path, methods in paths.items()
        if path.startswith("/api/v1/dashboard") and "get" in methods
    )


def test_every_dashboard_route_is_covered():
    assert len(dashboard_get_paths()) == 18


@pytest.mark.parametrize("path", dashboard_get_paths())
def test_every_dashboard_route_requires_a_management_session(path, anonymous_client, no_database):
    response = anonymous_client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", dashboard_get_paths())
def test_invalid_or_expired_token_is_rejected(path, anonymous_client, no_database):
    response = anonymous_client.get(path, headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_engineering_session_cannot_read_management_dashboard(monkeypatch, anonymous_client, no_database):
    token = engineering_auth.create_session("Alfie")["token"]

    try:
        response = anonymous_client.get(
            "/api/v1/dashboard/overview", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        engineering_auth._sessions.clear()

    assert response.status_code == 401


def test_dashboard_origin_without_session_gets_no_data(anonymous_client, no_database):
    response = anonymous_client.get("/api/v1/dashboard/summary", headers={"Origin": DASHBOARD_ORIGIN})

    assert response.status_code == 401
    assert "expected_tonnes" not in response.text


# ==========================================================
# HTTP: WINDOW ENDPOINTS
# ==========================================================


@pytest.fixture
def fixed_data(monkeypatch):
    calls = []

    def fake_window(start, end, production_line, shift_based=False):
        calls.append((start, end, production_line, shift_based))
        return window_data()

    monkeypatch.setattr(dashboard_api, "_utc_now", lambda: NOW)
    monkeypatch.setattr(dashboard_api, "get_dashboard_window_data", fake_window)
    return calls


def test_overview_defaults_to_current_shift(manager_client, fixed_data):
    response = manager_client.get("/api/v1/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["window"]["kind"] == "current_shift"
    # Shift windows select hourly output by operational shift instance.
    assert fixed_data == [(SHIFT.start, SHIFT.end, None, True)]
    assert {line["production_line"]: line["attention_status"] for line in body["lines"]} == {
        "Rovema": "red", "GIC": "green", "Guill": "grey",
    }


def test_operational_intelligence_reads_default_to_previous_24_hours(manager_client, fixed_data):
    window = rolling_24h_window(NOW)

    for path in ("gap-attribution", "machines", "engineering-classification", "xray-waste"):
        response = manager_client.get(f"/api/v1/dashboard/{path}")
        assert response.status_code == 200, path
        assert response.json()["window"]["kind"] == "rolling_24h"

    # Rolling 24h selects by period end, not by shift instance.
    assert all(call == (window.start, window.end, None, False) for call in fixed_data)


def test_lines_endpoint_and_line_filter(manager_client, fixed_data):
    lines = manager_client.get("/api/v1/dashboard/lines")
    filtered = manager_client.get(
        "/api/v1/dashboard/overview", params={"production_line": "GIC", "window": "factory_day"}
    )

    assert lines.status_code == 200
    assert len(lines.json()["lines"]) == 3
    assert filtered.status_code == 200
    assert fixed_data[-1][2] == "GIC"
    assert filtered.json()["window"]["kind"] == "factory_day"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/overview?window=fortnight",
        "/api/v1/dashboard/overview?production_line=Nowhere",
        "/api/v1/dashboard/weekly-targets?week_start=2026-01-13",
        "/api/v1/dashboard/changeovers?group_by=colour",
        "/api/v1/dashboard/changeovers?date_from=2026-01-13&date_to=2026-01-12",
        "/api/v1/dashboard/changeovers?shift=Evening",
    ],
)
def test_invalid_dashboard_queries_are_422(path, manager_client, fixed_data):
    assert manager_client.get(path).status_code == 422


def test_dashboard_database_failure_is_safe_503(manager_client, monkeypatch, capsys):
    def broken(*args):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(dashboard_api, "get_dashboard_window_data", broken)

    response = manager_client.get("/api/v1/dashboard/overview")

    assert response.status_code == 503
    captured = capsys.readouterr()
    assert "s3cr3t" not in response.text
    assert "s3cr3t" not in captured.out + captured.err


def test_weekly_targets_endpoint(manager_client, fixed_data, monkeypatch):
    requested = []

    def fake_targets(week_start):
        requested.append(week_start)
        return [{"scope": "site", "production_line": None, "target_tonnes": Decimal(100)}]

    monkeypatch.setattr(dashboard_api, "list_weekly_targets", fake_targets)

    response = manager_client.get("/api/v1/dashboard/weekly-targets")

    assert response.status_code == 200
    body = response.json()
    assert requested == [date(2026, 1, 12)]
    assert body["site"]["target_tonnes"] == 100.0
    assert body["site"]["target_status"] in ("green", "red")
    week = week_window_starting(date(2026, 1, 12))
    assert fixed_data == [(week.start, week.end, None, True)]


def test_changeovers_endpoint_converts_factory_days_and_groups(manager_client, monkeypatch):
    received = {}

    def fake_list(filters):
        received.update(filters)
        return CHANGEOVERS

    monkeypatch.setattr(dashboard_api, "list_changeovers", fake_list)
    monkeypatch.setattr(dashboard_api, "_utc_now", lambda: NOW)

    response = manager_client.get(
        "/api/v1/dashboard/changeovers",
        params={"date_from": "2026-01-12", "date_to": "2026-01-20", "production_line": "GIC",
                "shift": "Day", "group_by": "technician", "min_duration_minutes": 10},
    )

    assert response.status_code == 200
    assert received["started_from"] == factory_day_start(date(2026, 1, 12))
    assert received["started_to"] == factory_day_start(date(2026, 1, 21))
    assert received["production_line"] == "GIC"
    assert received["min_duration_minutes"] == 10
    assert response.json()["groups"][0]["key"] == "Liam"
