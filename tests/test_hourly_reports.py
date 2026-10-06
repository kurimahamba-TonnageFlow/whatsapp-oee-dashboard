"""
The fixed-hour Production report (src/hourly_reports.py) and its
protected endpoint GET /api/v1/dashboard/hourly. Synthetic rows only -
no database is touched.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from src import dashboard_api, hourly_reports, management_auth
from src.api import app
from src.factory_time import shift_window_for


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


DAY = shift_window_for(datetime(2026, 1, 12).date(), "Day")  # 06:00-14:00 GMT


def run(run_id, product, technician, start, end=None, speed=100):
    return {
        "id": run_id, "production_line": "Rovema", "line_technician": technician, "shift": "Days",
        "customer": "Asda", "product": product, "format": "Pillow", "pack_weight_kg": Decimal(1),
        "packs_per_case": 10, "cases_per_pallet": 10, "standard_speed_ppm": Decimal(speed), "target_speed_ppm": Decimal(speed),
        "status": "Completed" if end else "Active", "started_at": start, "finished_at": end,
    }


def reading(run_id, hour, pallets):
    return {"production_run_id": run_id, "hour_start": utc(2026, 1, 12, hour), "pallets_completed": Decimal(pallets)}


def shift_data():
    """Liam runs Basmati from 06:00; End Run at 08:20; changeover 08:20-08:40;
    Ben runs Jasmine from 08:40 at 50 ppm, speed raised to 60 at 10:30.
    A casepacker fault opened on Liam's run 07:50-09:10 carries over.
    Hour 09:00-10:00 of Ben's run was never reported."""
    return {
        "lines": ["Rovema", "GIC"],
        "runs": [
            run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8, 20)),
            run(2, "Jasmine", "Ben", utc(2026, 1, 12, 8, 40), speed=50),
        ],
        "readings": [
            reading(1, 6, 54),   # 5400 / 6000 = 90%
            reading(1, 7, 50),   # 5000 / 6000 = 83.3%
            reading(1, 8, 20),   # 2000 / 2000 (20 min) = 100%
            reading(2, 8, 10),   # 1000 / 1000 (20 min at 50) = 100%
            reading(2, 10, 20),  # 2000 / (30x50 + 30x60 = 3300) = 60.6%
        ],
        "speed_changes": [
            {"production_run_id": 2, "previous_speed_ppm": Decimal(50), "new_speed_ppm": Decimal(60),
             "effective_at": utc(2026, 1, 12, 10, 30)},
        ],
        "planned": [],
        "faults": [
            {"id": 7, "production_line": "Rovema", "machine": "Casepacker", "reason": "Open cases",
             "opened_at": utc(2026, 1, 12, 7, 50), "resolved_at": utc(2026, 1, 12, 9, 10)},
        ],
        "stoppages": [
            {"id": 11, "production_line": "Rovema", "kind": "changeover", "reason": None,
             "started_at": utc(2026, 1, 12, 8, 20), "ended_at": utc(2026, 1, 12, 8, 40),
             "previous_production_run_id": 1, "reference_speed_ppm": Decimal(100)},
        ],
    }


NOW = utc(2026, 1, 12, 11, 20)


@pytest.fixture
def report():
    return hourly_reports.build_hourly_report(shift_data(), DAY, NOW)


def hour(report, label, line="Rovema"):
    rows = next(l for l in report["lines"] if l["production_line"] == line)["hours"]
    return next(h for h in rows if h["hour_label"] == label)


def test_shows_every_hour_of_the_shift_so_far_and_not_the_future(report):
    labels = [h["hour_label"] for h in report["lines"][0]["hours"]]
    assert labels == ["06:00–07:00", "07:00–08:00", "08:00–09:00", "09:00–10:00", "10:00–11:00", "11:00–12:00"]
    assert report["measure"] == "Output vs target (all stops)"
    assert "not OEE" in report["method"]


def test_a_reported_hour_shows_product_technician_and_speeds(report):
    first = hour(report, "06:00–07:00")
    run_row = first["runs"][0]
    assert (run_row["product"], run_row["line_technician"]) == ("Basmati", "Liam")
    assert run_row["output_vs_target_percent"] == 90.0
    assert run_row["actual_speed_ppm"] == 90.0
    assert run_row["target_speeds"][0]["speed_ppm"] == 100.0
    assert first["line"]["output_vs_target_percent"] == 90.0
    assert not first["line"]["is_low_output"]


def test_a_carried_fault_is_shown_beside_the_result_and_counted_once(report):
    seven = hour(report, "07:00–08:00")
    assert seven["line"]["unplanned_minutes"] == 10.0
    assert seven["line"]["stop_reasons"] == [{"kind": "unplanned", "reason": "Casepacker — Open cases", "minutes": 10.0}]
    # The fault opened on Liam's run still stops Ben's run after the changeover.
    nine_ben = hour(report, "09:00–10:00")["runs"][0]
    assert nine_ben["line_technician"] == "Ben"
    assert nine_ben["unplanned_minutes"] == 10.0


def test_the_changeover_hour_splits_runs_and_charges_the_changeover_to_the_line_only(report):
    eight = hour(report, "08:00–09:00")
    runs = {r["product"]: r for r in eight["runs"]}
    assert runs["Basmati"]["applicable_minutes"] == 20.0
    assert runs["Basmati"]["output_vs_target_percent"] == 100.0
    assert runs["Jasmine"]["applicable_minutes"] == 20.0
    assert runs["Jasmine"]["output_vs_target_percent"] == 100.0
    # Line: 3000 actual / (2000 + 1000 + 20 min x 100 ppm) = 60%.
    assert eight["line"]["target_packs"] == 5000.0
    assert eight["line"]["output_vs_target_percent"] == 60.0
    assert eight["line"]["planned_minutes"] == 20.0
    # The fault (07:50-09:10) overlaps the changeover; those minutes stay planned.
    assert eight["line"]["unplanned_minutes"] == 40.0
    assert eight["line"]["stopped_minutes"] == 60.0


def test_a_missed_hour_is_no_reading_not_zero(report):
    nine = hour(report, "09:00–10:00")
    assert nine["line"]["status"] == "no_reading"
    assert nine["line"]["output_vs_target_percent"] is None
    assert nine["runs"][0]["status"] == "no_reading"
    assert nine["runs"][0]["actual_packs"] is None


def test_a_mid_hour_speed_change_splits_the_target_and_below_sixty_is_low(report):
    ten = hour(report, "10:00–11:00")["runs"][0]
    assert [s["speed_ppm"] for s in ten["target_speeds"]] == [50.0]
    assert ten["target_packs"] == 3000.0
    assert ten["output_vs_target_percent"] == 66.7
    assert not ten["is_low_output"]
    seven = hour(report, "07:00–08:00")
    assert seven["line"]["output_vs_target_percent"] == 83.3


def test_the_current_hour_is_in_progress_and_the_latest_completed_hour_is_the_one_before(report):
    eleven = hour(report, "11:00–12:00")
    assert eleven["line"]["status"] == "in_progress"
    assert not eleven["is_complete"]
    assert report["lines"][0]["latest_completed_hour"]["hour_label"] == "10:00–11:00"


def test_a_line_with_nothing_running_has_idle_hours_and_no_latest_hour(report):
    gic = next(l for l in report["lines"] if l["production_line"] == "GIC")
    assert gic["latest_completed_hour"] is None
    # Nothing ran and nothing was stopped: every hour is idle, including the current one.
    assert {h["line"]["status"] for h in gic["hours"]} == {"idle"}


def test_low_output_is_flagged_below_sixty_percent():
    data = shift_data()
    data["readings"] = [reading(1, 6, 30)]  # 50%
    report = hourly_reports.build_hourly_report(data, DAY, utc(2026, 1, 12, 7, 5), "Rovema")
    first = report["lines"][0]["hours"][0]
    assert first["line"]["is_low_output"] and first["runs"][0]["is_low_output"]


def test_autumn_night_shift_has_nine_hours():
    night = shift_window_for(datetime(2026, 10, 24).date(), "Night")
    data = {"lines": ["Rovema"], "runs": [], "readings": [], "speed_changes": [], "planned": [], "faults": [],
            "stoppages": []}
    report = hourly_reports.build_hourly_report(data, night, night.end + timedelta(hours=1))
    assert len(report["lines"][0]["hours"]) == 9


# ----------------------------------------------------------
# HTTP
# ----------------------------------------------------------


@pytest.fixture
def manager_client(monkeypatch):
    monkeypatch.setattr(management_auth, "MANAGEMENT_PIN", "test-pin")
    management_auth._sessions.clear()
    token = management_auth.create_session("Test Manager")["token"]
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"})
    management_auth._sessions.clear()


def test_hourly_endpoint_reads_the_requested_shift(manager_client, monkeypatch):
    calls = []

    def fake(start, end, line):
        calls.append((start, end, line))
        return shift_data()

    monkeypatch.setattr(dashboard_api, "get_hourly_report_data", fake)
    monkeypatch.setattr(dashboard_api, "_utc_now", lambda: NOW)

    response = manager_client.get("/api/v1/dashboard/hourly?shift_offset=1&production_line=Rovema")

    assert response.status_code == 200
    # 11:20 is the Day shift; one back is the previous Night (22:00-06:00).
    assert calls == [(utc(2026, 1, 11, 22), utc(2026, 1, 12, 6), "Rovema")]
    assert response.json()["measure"] == "Output vs target (all stops)"


def test_hourly_endpoint_requires_a_management_session():
    assert TestClient(app).get("/api/v1/dashboard/hourly").status_code == 401


def test_hourly_endpoint_rejects_an_unknown_line(manager_client):
    assert manager_client.get("/api/v1/dashboard/hourly?production_line=Nowhere").status_code == 422


def test_handover_across_an_hour_boundary_counts_once_on_the_line_in_each_hour():
    """Liam ends shift at 08:50, Ben starts at 09:10: the 20-minute
    handover is split 10 + 10 across the two hours, on the line only."""
    data = {
        "lines": ["Rovema"],
        "runs": [
            run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8, 50)),
            run(2, "Basmati", "Ben", utc(2026, 1, 12, 9, 10)),
        ],
        "readings": [reading(1, 8, 50), reading(2, 9, 50)],
        "speed_changes": [], "planned": [], "faults": [],
        "stoppages": [
            {"id": 12, "production_line": "Rovema", "kind": "handover", "reason": None,
             "started_at": utc(2026, 1, 12, 8, 50), "ended_at": utc(2026, 1, 12, 9, 10),
             "physical_ended_at": None, "started_by": "Liam", "ended_by": "Ben",
             "previous_production_run_id": 1, "reference_speed_ppm": Decimal(100)},
        ],
    }
    report = hourly_reports.build_hourly_report(data, DAY, NOW, "Rovema")
    eight, nine = hour(report, "08:00–09:00"), hour(report, "09:00–10:00")

    for slot in (eight, nine):
        assert slot["line"]["planned_minutes"] == 10.0
        assert slot["line"]["stop_reasons"] == [
            {"kind": "planned", "reason": "Handover (Liam → Ben)", "minutes": 10.0}
        ]
        assert slot["line"]["unaccounted_minutes"] == 0.0
        # Neither product run is charged: each run's own result ignores it.
        assert slot["runs"][0]["stopped_minutes"] == 0.0
    # Line: 5000 / (5000 + 10 x 100) = 83.3%; the run alone is 100%.
    assert eight["runs"][0]["output_vs_target_percent"] == 100.0
    assert eight["line"]["output_vs_target_percent"] == 83.3
    assert (eight["runs"][0]["line_technician"], nine["runs"][0]["line_technician"]) == ("Liam", "Ben")


def test_changeover_total_runs_through_the_new_run_form_and_is_split_physical_and_setup():
    data = shift_data()
    data["stoppages"][0]["physical_ended_at"] = utc(2026, 1, 12, 8, 32)
    report = hourly_reports.build_hourly_report(data, DAY, NOW)
    eight = hour(report, "08:00–09:00")

    reasons = {r["reason"]: r["minutes"] for r in eight["line"]["stop_reasons"]}
    assert reasons["Changeover — physical work"] == 12.0
    assert reasons["Changeover — new-run setup"] == 8.0
    # Counted once: the fault overlapping it does not add changeover time twice.
    assert eight["line"]["planned_minutes"] == 20.0
    assert eight["line"]["target_packs"] == 5000.0


def other_then_restart_delay():
    """Liam ends at 08:10. Other 'Power cut' 08:10-08:50 (resolved by Ben);
    Restart delay 08:50-09:25; Ben starts 09:25."""
    return {
        "lines": ["Rovema"],
        "runs": [
            run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8, 10)),
            run(2, "Basmati", "Ben", utc(2026, 1, 12, 9, 25)),
        ],
        "readings": [reading(1, 8, 10), reading(2, 9, 35)],
        "speed_changes": [], "planned": [], "faults": [],
        "stoppages": [
            {"id": 21, "production_line": "Rovema", "kind": "other", "reason": "Power cut",
             "started_at": utc(2026, 1, 12, 8, 10), "ended_at": utc(2026, 1, 12, 8, 50),
             "physical_ended_at": None, "started_by": "Liam", "ended_by": "Ben",
             "previous_production_run_id": 1, "reference_speed_ppm": Decimal(100)},
            {"id": 22, "production_line": "Rovema", "kind": "restart_delay", "reason": "Power cut",
             "started_at": utc(2026, 1, 12, 8, 50), "ended_at": utc(2026, 1, 12, 9, 25),
             "physical_ended_at": None, "started_by": "Ben", "ended_by": "Ben",
             "previous_production_run_id": 1, "reference_speed_ppm": Decimal(100)},
        ],
    }


def test_other_and_restart_delay_are_separate_unplanned_reasons_counted_once():
    report = hourly_reports.build_hourly_report(other_then_restart_delay(), DAY, NOW, "Rovema")
    eight, nine = hour(report, "08:00–09:00"), hour(report, "09:00–10:00")

    assert eight["line"]["stop_reasons"] == [
        {"kind": "unplanned", "reason": "Other: Power cut", "minutes": 40.0},
        {"kind": "unplanned", "reason": "Restart delay", "minutes": 10.0},
    ]
    assert nine["line"]["stop_reasons"] == [{"kind": "unplanned", "reason": "Restart delay", "minutes": 25.0}]
    # Once on the line: 10 min run + 40 + 10 = the whole hour, nothing unaccounted.
    assert eight["line"]["unplanned_minutes"] == 50.0
    assert eight["line"]["unaccounted_minutes"] == 0.0
    # 1000 packs / (1000 + 50 x 100) - neither run is charged.
    assert eight["line"]["output_vs_target_percent"] == 16.7
    assert eight["runs"][0]["stopped_minutes"] == 0.0
    assert nine["runs"][0]["stopped_minutes"] == 0.0


def test_a_restart_delay_still_open_into_the_next_day_counts_up_to_now():
    """Resolved at 21:30 the day before and still waiting for a run: the
    open delay is counted in every hour of today's shift so far."""
    data = {
        "lines": ["Rovema"], "runs": [], "readings": [], "speed_changes": [], "planned": [], "faults": [],
        "stoppages": [
            {"id": 22, "production_line": "Rovema", "kind": "restart_delay", "reason": "Power cut",
             "started_at": utc(2026, 1, 11, 21, 30), "ended_at": None, "physical_ended_at": None,
             "started_by": "Ben", "ended_by": None, "previous_production_run_id": 1,
             "reference_speed_ppm": Decimal(100)},
        ],
    }
    report = hourly_reports.build_hourly_report(data, DAY, utc(2026, 1, 12, 7, 30), "Rovema")
    six, seven = hour(report, "06:00–07:00"), hour(report, "07:00–08:00")

    assert six["line"]["stop_reasons"] == [{"kind": "unplanned", "reason": "Restart delay", "minutes": 60.0}]
    assert six["line"]["output_vs_target_percent"] == 0.0
    assert seven["line"]["stop_reasons"] == [{"kind": "unplanned", "reason": "Restart delay", "minutes": 30.0}]


def not_scheduled_stop(start, end, stop_id=40, previous=1):
    return {"id": stop_id, "production_line": "Rovema", "kind": "not_scheduled", "reason": None,
            "started_at": start, "ended_at": end, "physical_ended_at": None, "started_by": "Liam",
            "ended_by": None, "previous_production_run_id": previous, "reference_speed_ppm": Decimal(100)}


def quiet(stoppages, runs=(), readings=(), faults=()):
    return {"lines": ["Rovema"], "runs": list(runs), "readings": list(readings), "speed_changes": [],
            "planned": [], "faults": list(faults), "stoppages": stoppages}


def test_not_scheduled_hours_have_no_target_no_downtime_and_no_percentage():
    """Liam ends at 08:00; the line is not scheduled until further notice.
    A carried fault open 07:50-09:10 is not charged for the unscheduled time."""
    data = quiet(
        [not_scheduled_stop(utc(2026, 1, 12, 8), None)],
        runs=[run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8))],
        readings=[reading(1, 6, 60), reading(1, 7, 60)],
        faults=[{"id": 7, "production_line": "Rovema", "machine": "Casepacker", "reason": "Open cases",
                 "opened_at": utc(2026, 1, 12, 7, 50), "resolved_at": utc(2026, 1, 12, 9, 10)}],
    )
    report = hourly_reports.build_hourly_report(data, DAY, NOW, "Rovema")

    for label in ("08:00–09:00", "09:00–10:00", "10:00–11:00"):
        line = hour(report, label)["line"]
        assert line["status"] == "not_scheduled"
        assert line["output_vs_target_percent"] is None and line["target_packs"] == 0.0
        assert line["stopped_minutes"] == 0.0 and line["unplanned_minutes"] == 0.0
        assert line["planned_minutes"] == 0.0 and line["unaccounted_minutes"] == 0.0
        assert line["not_scheduled_minutes"] == 60.0
        assert line["stop_reasons"] == [{"kind": "not_scheduled", "reason": "Not scheduled", "minutes": 60.0}]
    # The fault still counts inside the scheduled run time.
    assert hour(report, "07:00–08:00")["line"]["unplanned_minutes"] == 10.0
    # A wholly unscheduled hour is never "the latest completed hour".
    assert report["lines"][0]["latest_completed_hour"]["hour_label"] == "07:00–08:00"


def test_a_part_not_scheduled_hour_is_judged_on_its_scheduled_minutes_only():
    """Run 06:00-08:20 makes its 20-minute target; 40 min not scheduled."""
    data = quiet(
        [not_scheduled_stop(utc(2026, 1, 12, 8, 20), utc(2026, 1, 12, 9, 30))],
        runs=[run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8, 20)),
              run(2, "Basmati", "Ben", utc(2026, 1, 12, 9, 30))],
        readings=[reading(1, 8, 20), reading(2, 9, 30)],
    )
    eight = hour(hourly_reports.build_hourly_report(data, DAY, NOW, "Rovema"), "08:00–09:00")["line"]

    assert eight["output_vs_target_percent"] == 100.0        # 2000 / 2000, not 2000 / 6000
    assert eight["not_scheduled_minutes"] == 40.0
    assert eight["stopped_minutes"] == 0.0 and eight["unaccounted_minutes"] == 0.0


def test_not_scheduled_across_a_shift_boundary_is_counted_once_in_each_shift():
    """06:00-12:30 run, not scheduled 12:30-14:30 (Day ends 14:00 GMT), then a run."""
    data = quiet(
        [not_scheduled_stop(utc(2026, 1, 12, 12, 30), utc(2026, 1, 12, 14, 30))],
        runs=[run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 12, 30)),
              run(2, "Basmati", "Ben", utc(2026, 1, 12, 14, 30))],
    )
    now = utc(2026, 1, 12, 16, 0)
    day = hourly_reports.build_hourly_report(data, DAY, now, "Rovema")
    afternoon = hourly_reports.build_hourly_report(
        data, shift_window_for(datetime(2026, 1, 12).date(), "Afternoon"), now, "Rovema"
    )

    minutes = [slot["line"]["not_scheduled_minutes"] for rep in (day, afternoon) for slot in rep["lines"][0]["hours"]]
    assert sum(minutes) == 120.0                      # the whole interval, once
    assert hour(day, "12:00–13:00")["line"]["not_scheduled_minutes"] == 30.0
    assert hour(afternoon, "14:00–15:00")["line"]["not_scheduled_minutes"] == 30.0


@pytest.mark.parametrize(
    "night_of, hours",
    [
        (datetime(2026, 10, 24), 9),   # BST -> GMT: the night has 9 clock hours, crossing midnight
        (datetime(2027, 3, 27), 7),    # GMT -> BST: 7
    ],
)
def test_not_scheduled_through_a_clock_change_night_covers_every_real_hour_once(night_of, hours):
    night = shift_window_for(night_of.date(), "Night")
    data = quiet([not_scheduled_stop(night.start - timedelta(hours=2), night.end + timedelta(hours=1))])
    report = hourly_reports.build_hourly_report(data, night, night.end + timedelta(hours=3), "Rovema")

    slots = report["lines"][0]["hours"]
    assert len(slots) == hours
    assert all(slot["line"]["status"] == "not_scheduled" for slot in slots)
    assert sum(slot["line"]["not_scheduled_minutes"] for slot in slots) == hours * 60.0
    assert all(slot["line"]["stopped_minutes"] == 0.0 for slot in slots)
    assert report["lines"][0]["latest_completed_hour"] is None


def test_a_reclassification_moves_the_same_minutes_from_unplanned_to_not_scheduled():
    """The same interval, before and after a manager correction: nothing
    is added or counted twice - the minutes simply change classification."""
    runs = [run(1, "Basmati", "Liam", utc(2026, 1, 12, 6), utc(2026, 1, 12, 8))]
    readings = [reading(1, 6, 60), reading(1, 7, 60)]
    as_other = {**not_scheduled_stop(utc(2026, 1, 12, 8), utc(2026, 1, 12, 10)), "kind": "other", "reason": "No orders"}
    before = hourly_reports.build_hourly_report(quiet([as_other], runs, readings), DAY, NOW, "Rovema")
    after = hourly_reports.build_hourly_report(
        quiet([{**as_other, "kind": "not_scheduled", "reason": None}], runs, readings), DAY, NOW, "Rovema"
    )

    b, a = hour(before, "08:00–09:00")["line"], hour(after, "08:00–09:00")["line"]
    assert (b["unplanned_minutes"], b["not_scheduled_minutes"], b["output_vs_target_percent"]) == (60.0, 0.0, 0.0)
    assert (a["unplanned_minutes"], a["not_scheduled_minutes"], a["output_vs_target_percent"]) == (0.0, 60.0, None)
    assert b["covered_minutes"] == a["covered_minutes"] == 60.0
