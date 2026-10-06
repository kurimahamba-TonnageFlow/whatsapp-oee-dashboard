"""
Fixed clock-hour reporting: the pure calculations in src/factory_time.py
and src/pulse_calculations.py. No database, no network, no clock.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import factory_time as ft
from src import pulse_calculations as calc


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


PPP = Decimal(100)  # packs per pallet in these tests


def test_short_recorded_stop_does_not_hide_remaining_output_loss():
    start, end = utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)
    result = calc.unexplained_hour_loss([(start, Decimal(100))], start, end, 3000,
                                      [(start, start + timedelta(minutes=2))])
    assert result['remaining_gap_packs'] == 2800
    assert result['equivalent_minutes'] == 28
    assert result['prompt_required'] is True


def test_overlapping_stops_are_counted_once_and_clipped_to_hour():
    start, end = utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)
    result = calc.unexplained_hour_loss([(start, Decimal(100))], start, end, 3000,
        [(start-timedelta(minutes=30), start+timedelta(minutes=10)),
         (start, start+timedelta(minutes=20))])
    assert result['equivalent_minutes'] == 10
    assert result['prompt_required'] is True


def test_loss_threshold_uses_unrounded_minutes():
    start, end = utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)
    result = calc.unexplained_hour_loss([(start, Decimal(100))], start, end, 5001, [])
    assert result['prompt_required'] is False
    assert calc.unexplained_hour_loss([(start, Decimal(100))], start, end, 5000, [])['prompt_required'] is True


def test_loss_review_uses_historical_speed_and_never_negative_loss():
    start, end = utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)
    timeline = [(start, Decimal(100)), (start+timedelta(minutes=30), Decimal(200))]
    result = calc.unexplained_hour_loss(timeline, start, end, 3000,
                                      [(start+timedelta(minutes=30), start+timedelta(minutes=40))])
    assert result['target_packs'] == 9000
    assert result['remaining_gap_packs'] == 4000
    assert result['equivalent_minutes'] == 26.7
    assert calc.unexplained_hour_loss(timeline, start, end, 10000, [])['remaining_gap_packs'] == 0


# ----------------------------------------------------------
# Clock hours, shifts and daylight saving
# ----------------------------------------------------------


def test_a_clock_hour_is_a_utc_hour_boundary_in_gmt_and_bst():
    assert ft.is_clock_hour_start(utc(2026, 1, 12, 6))
    assert ft.is_clock_hour_start(utc(2026, 7, 13, 5))  # 06:00 BST
    assert not ft.is_clock_hour_start(utc(2026, 1, 12, 6, 30))
    assert ft.clock_hour_start(utc(2026, 1, 12, 7, 10, 5)) == utc(2026, 1, 12, 7)


def test_day_shift_has_eight_named_hours_in_gmt():
    window = ft.shift_window_for(datetime(2026, 1, 12).date(), "Day")
    hours = ft.clock_hours_between(window.start, window.end)
    assert len(hours) == 8
    assert [ft.clock_hour_label(h) for h in hours[:2]] == ["06:00–07:00", "07:00–08:00"]
    assert ft.clock_hour_label(hours[-1]) == "13:00–14:00"


def test_day_shift_hours_are_an_hour_earlier_in_utc_during_bst():
    window = ft.shift_window_for(datetime(2026, 7, 13).date(), "Day")
    hours = ft.clock_hours_between(window.start, window.end)
    assert hours[0] == utc(2026, 7, 13, 5)
    assert ft.clock_hour_label(hours[0]) == "06:00–07:00"


def test_night_shift_crosses_midnight_into_one_shift_instance():
    window = ft.shift_window_for(datetime(2026, 1, 12).date(), "Night")
    hours = ft.clock_hours_between(window.start, window.end)
    assert len(hours) == 8
    labels = [ft.clock_hour_label(h) for h in hours]
    assert labels[1] == "23:00–00:00" and labels[2] == "00:00–01:00"
    # A moment after midnight belongs to the Night shift that started the evening before.
    assert ft.shift_window_containing(utc(2026, 1, 13, 2, 30)).start == window.start


def test_spring_night_has_seven_hours_and_no_0100_slot():
    # Clocks go forward at 01:00 GMT on Sunday 29 March 2026.
    window = ft.shift_window_for(datetime(2026, 3, 28).date(), "Night")
    hours = ft.clock_hours_between(window.start, window.end)
    labels = [ft.clock_hour_label(h) for h in hours]
    assert len(hours) == 7
    assert "00:00 GMT–02:00 BST" in labels
    assert not any(label.startswith("01:00") for label in labels)


def test_autumn_night_has_nine_hours_and_two_different_0100_slots():
    # Clocks go back at 02:00 BST on Sunday 25 October 2026.
    window = ft.shift_window_for(datetime(2026, 10, 24).date(), "Night")
    hours = ft.clock_hours_between(window.start, window.end)
    labels = [ft.clock_hour_label(h) for h in hours]
    assert len(hours) == 9
    assert "01:00 BST–01:00 GMT" in labels
    assert "01:00 GMT–02:00 GMT" in labels
    assert len(set(labels)) == 9


def test_previous_shift_offsets():
    now = utc(2026, 1, 12, 15)  # Afternoon
    assert ft.shift_window_offset(now, 0).label.startswith("Afternoon")
    assert ft.shift_window_offset(now, 1).label.startswith("Day")
    assert ft.shift_window_offset(now, 2).label.startswith("Night shift 2026-01-11")


# ----------------------------------------------------------
# Target speed timeline (mid-run changes apply forward only)
# ----------------------------------------------------------


def change(at_time, old, new):
    return {"effective_at": at_time, "previous_speed_ppm": Decimal(old), "new_speed_ppm": Decimal(new)}


def test_no_change_uses_the_runs_speed_throughout():
    timeline = calc.speed_timeline(Decimal(100), [])
    assert calc.target_packs_between(timeline, utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)) == Decimal(6000)


def test_mid_hour_speed_change_splits_the_hour_by_the_speed_in_force():
    # 100 ppm until 06:20, then 120 ppm: 20 x 100 + 40 x 120 = 6800.
    timeline = calc.speed_timeline(Decimal(120), [change(utc(2026, 1, 12, 6, 20), 100, 120)])
    assert calc.target_packs_between(timeline, utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)) == Decimal(6800)
    segments = calc.speed_segments(timeline, utc(2026, 1, 12, 6), utc(2026, 1, 12, 7))
    assert [s[2] for s in segments] == [Decimal(100), Decimal(120)]


def test_a_speed_change_never_rewrites_earlier_hours():
    timeline = calc.speed_timeline(Decimal(120), [change(utc(2026, 1, 12, 7, 30), 100, 120)])
    assert calc.target_packs_between(timeline, utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)) == Decimal(6000)


def test_two_changes_in_one_hour():
    timeline = calc.speed_timeline(
        Decimal(90),
        [change(utc(2026, 1, 12, 6, 30), 100, 120), change(utc(2026, 1, 12, 6, 10), 80, 100)],
    )
    # 10 x 80 + 20 x 100 + 30 x 120 = 6400
    assert calc.target_packs_between(timeline, utc(2026, 1, 12, 6), utc(2026, 1, 12, 7)) == Decimal(6400)


# ----------------------------------------------------------
# Stops: every minute counted once
# ----------------------------------------------------------

H6 = utc(2026, 1, 12, 6)


def at(minutes):
    return H6 + timedelta(minutes=minutes)


def test_overlapping_faults_are_counted_once():
    stops = calc.classify_stops(
        [(H6, at(60))], [], [(at(10), at(30), "Jam"), (at(20), at(40), "Film")]
    )
    assert stops["unplanned_minutes"] == Decimal(30)
    assert stops["stopped_minutes"] == Decimal(30)
    assert {r["reason"]: r["minutes"] for r in stops["reasons"]} == {"Jam": Decimal(20), "Film": Decimal(20)}


def test_a_fault_inside_a_planned_stop_counts_once_as_planned():
    stops = calc.classify_stops([(H6, at(60))], [(at(0), at(30), "Cleaning")], [(at(20), at(40), "Jam")])
    assert stops["planned_minutes"] == Decimal(30)
    assert stops["unplanned_minutes"] == Decimal(10)
    assert stops["stopped_minutes"] == Decimal(40)


def test_stops_outside_the_applicable_time_are_ignored():
    stops = calc.classify_stops([(at(30), at(60))], [], [(at(0), at(40), "Jam")])
    assert stops["unplanned_minutes"] == Decimal(10)


# ----------------------------------------------------------
# One product run, one clock hour
# ----------------------------------------------------------

NOW = utc(2026, 1, 12, 12)


def run_hour(hour, pallets, run_start=utc(2026, 1, 12, 5), run_end=None, speed=100, now=NOW,
             planned=(), unplanned=(), changes=()):
    return calc.run_hour_result(
        hour, now, run_start, run_end, calc.speed_timeline(Decimal(speed), list(changes)),
        PPP, pallets, list(planned), list(unplanned),
    )


def test_a_reported_full_hour():
    result = run_hour(H6, Decimal("54"))  # 5400 of 6000 packs
    assert result["status"] == "reported"
    assert result["target_packs"] == Decimal(6000)
    assert result["actual_packs"] == Decimal(5400)
    assert result["output_vs_target_percent"] == Decimal(90)
    assert result["actual_speed_ppm"] == Decimal(90)
    assert not result["is_partial_hour"]


def test_stops_lower_the_percentage_and_are_not_subtracted_again():
    # 20 min stopped; 40 min at full speed = 4000 packs = 66.7% of the
    # full hour's target. Were stopped time taken out of the target the
    # result would wrongly read 100%.
    result = run_hour(H6, Decimal(40), planned=[(at(0), at(10), "Cleaning")], unplanned=[(at(30), at(40), "Jam")])
    assert result["target_packs"] == Decimal(6000)
    assert result["stopped_minutes"] == Decimal(20)
    assert result["output_vs_target_percent"].quantize(Decimal("0.1")) == Decimal("66.7")


def test_an_unreported_hour_is_no_reading_never_zero():
    result = run_hour(H6, None)
    assert result["status"] == "no_reading"
    assert result["actual_packs"] is None
    assert result["output_vs_target_percent"] is None


def test_the_current_hour_is_in_progress_and_not_scored():
    result = run_hour(utc(2026, 1, 12, 11), Decimal(10), now=utc(2026, 1, 12, 11, 25))
    assert result["status"] == "in_progress"
    assert result["output_vs_target_percent"] is None
    assert result["applicable_minutes"] == Decimal(25)


def test_partial_first_hour_uses_only_the_minutes_after_the_run_started():
    result = run_hour(H6, Decimal(30), run_start=at(25))
    assert result["applicable_minutes"] == Decimal(35)
    assert result["is_partial_hour"]
    assert result["target_packs"] == Decimal(3500)
    assert result["output_vs_target_percent"].quantize(Decimal("0.1")) == Decimal("85.7")


def test_partial_last_hour_ends_when_the_run_ended():
    result = run_hour(H6, Decimal(40), run_end=at(40))
    assert result["applicable_minutes"] == Decimal(40)
    assert result["target_packs"] == Decimal(4000)
    assert result["output_vs_target_percent"] == Decimal(100)


def test_an_hour_outside_the_run_has_no_result():
    assert run_hour(utc(2026, 1, 12, 4), Decimal(1)) is None
    assert run_hour(utc(2026, 1, 12, 9), Decimal(1), run_end=utc(2026, 1, 12, 9)) is None


def test_mid_hour_speed_change_in_a_reported_hour():
    result = run_hour(H6, Decimal(68), speed=120, changes=[change(at(20), 100, 120)])
    assert result["target_packs"] == Decimal(6800)
    assert result["output_vs_target_percent"] == Decimal(100)
    assert [s["speed_ppm"] for s in result["target_speeds"]] == [Decimal(100), Decimal(120)]


def test_low_output_threshold_is_below_sixty_percent():
    assert calc.is_low_output(Decimal("59.9"))
    assert not calc.is_low_output(Decimal(60))
    assert not calc.is_low_output(None)


# ----------------------------------------------------------
# The line: product runs + changeover / other stops
# ----------------------------------------------------------


def test_changeover_lowers_the_line_hour_without_being_charged_to_either_run():
    # Old run 06:00-06:20 (100 ppm), changeover 06:20-06:40, new run 06:40-07:00 (50 ppm).
    old = run_hour(H6, Decimal(20), run_end=at(20))  # 2000 of 2000 = 100%
    new = run_hour(H6, Decimal(10), run_start=at(40), speed=50)  # 1000 of 1000 = 100%
    assert old["output_vs_target_percent"] == Decimal(100)
    assert new["output_vs_target_percent"] == Decimal(100)

    line = calc.line_hour_result(
        H6, NOW, [old, new],
        [{"start": at(20), "end": at(40), "kind": "changeover", "reason": "Changeover",
          "reference_speed_ppm": Decimal(100)}],
        [(at(20), at(40), "Changeover")], [],
    )
    # Denominator: 2000 + 1000 + 20 min x 100 ppm = 5000; actual 3000.
    assert line["target_packs"] == Decimal(5000)
    assert line["output_vs_target_percent"] == Decimal(60)
    assert line["planned_minutes"] == Decimal(20)
    assert line["unaccounted_minutes"] == Decimal(0)


def test_other_stop_is_unplanned_on_the_line():
    old = run_hour(H6, Decimal(30), run_end=at(30))
    line = calc.line_hour_result(
        H6, NOW, [old],
        [{"start": at(30), "end": at(60), "kind": "other", "reason": "Power cut",
          "reference_speed_ppm": Decimal(100)}],
        [], [(at(30), at(60), "Power cut")],
    )
    assert line["unplanned_minutes"] == Decimal(30)
    assert line["output_vs_target_percent"] == Decimal(50)


def test_a_handover_gap_is_unaccounted_not_invented():
    outgoing = run_hour(H6, Decimal(50), run_end=at(50))
    incoming = run_hour(H6, Decimal(5), run_start=at(55))
    line = calc.line_hour_result(H6, NOW, [outgoing, incoming], [], [], [])
    assert line["unaccounted_minutes"] == Decimal(5)
    assert line["target_packs"] == Decimal(5500)


def test_one_missing_run_reading_makes_the_line_hour_no_reading():
    old = run_hour(H6, Decimal(20), run_end=at(20))
    new = run_hour(H6, None, run_start=at(20))
    line = calc.line_hour_result(H6, NOW, [old, new], [], [], [])
    assert line["status"] == "no_reading"
    assert line["output_vs_target_percent"] is None


def test_a_carried_fault_across_two_runs_is_counted_once_on_the_line():
    old = run_hour(H6, Decimal(20), run_end=at(30), unplanned=[(at(10), at(50), "Jam")])
    new = run_hour(H6, Decimal(20), run_start=at(30), unplanned=[(at(10), at(50), "Jam")])
    assert old["unplanned_minutes"] == Decimal(20)
    assert new["unplanned_minutes"] == Decimal(20)
    line = calc.line_hour_result(H6, NOW, [old, new], [], [], [(at(10), at(50), "Jam")])
    assert line["unplanned_minutes"] == Decimal(40)


def test_an_idle_line_is_idle_even_in_the_current_hour():
    line = calc.line_hour_result(H6, at(20), [], [], [], [])
    assert line["status"] == "idle"
    assert line["output_vs_target_percent"] is None


def test_an_hour_wholly_in_a_changeover_is_zero_output_not_no_reading():
    line = calc.line_hour_result(
        H6, NOW, [],
        [{"start": at(0), "end": at(60), "kind": "changeover", "reason": "Changeover",
          "reference_speed_ppm": Decimal(100)}],
        [(at(0), at(60), "Changeover")], [],
    )
    assert line["status"] == "stopped"
    assert line["actual_packs"] == Decimal(0)
    assert line["output_vs_target_percent"] == Decimal(0)
