"""
Offline tests for src/pulse_calculations.py - the Phase 1 calculation
authority. Pure functions only: no database, network or real clock.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src import pulse_calculations as calc
from src.factory_time import week_window_starting


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# 8.4 packs/min, 10 packs/case, 10 cases/pallet (100 packs/pallet), 1 kg packs.
CONFIG = calc.PackConfig(Decimal("8.4"), Decimal(10), Decimal(10), Decimal("1"))

# A realistic Rovema-style config: 120 ppm, 8 packs/case, 220 cases/pallet.
ROVEMA = calc.PackConfig(Decimal(120), Decimal(8), Decimal(220), Decimal("1.000"))


def fresh_progress(remaining=25):
    return {"pallets_remaining": remaining, "total_pallets_completed": 0, "potential_overrun_pallets": 0}


# ==========================================================
# DECIMAL PALLETS AND CONVERSIONS
# ==========================================================


def test_decimal_pallets_convert_exactly_to_packs_and_tonnes():
    assert CONFIG.pallets_to_packs(Decimal("3.75")) == Decimal("375.00")
    assert CONFIG.packs_to_tonnes(Decimal(375)) == Decimal("0.375")
    assert CONFIG.packs_to_pallets(Decimal(375)) == Decimal("3.75")


def test_float_input_is_converted_via_its_shortest_repr_not_binary_expansion():
    assert calc.to_decimal(3.75) == Decimal("3.75")
    assert calc.to_decimal(0.1) == Decimal("0.1")


def test_realistic_pack_configuration_conversions():
    assert ROVEMA.packs_per_pallet == Decimal(1760)
    assert ROVEMA.pallets_to_packs(Decimal("3.75")) == Decimal("6600.000")
    assert ROVEMA.packs_to_tonnes(Decimal(6600)) == Decimal("6.6")
    assert ROVEMA.minutes_to_packs(Decimal(60)) == Decimal(7200)


def test_hourly_update_values_for_a_decimal_pallet_hour():
    values = calc.hourly_update_values(CONFIG, Decimal("3.75"), Decimal(60), Decimal(0), fresh_progress())

    assert values["expected_packs"] == Decimal("504.0000")
    assert values["actual_packs"] == Decimal("375.0000")
    assert values["expected_pallets"] == Decimal("5.0400")
    assert values["production_variance_packs"] == Decimal("-129.0000")
    assert values["estimated_lost_packs"] == Decimal("129.0000")
    assert values["pallets_remaining"] == Decimal("21.2500")
    assert values["total_pallets_completed"] == Decimal("3.7500")


def test_fractional_pallets_carry_through_many_updates_without_drift():
    progress = fresh_progress(remaining=Decimal(10))

    for _ in range(8):
        values = calc.hourly_update_values(CONFIG, Decimal("1.1"), Decimal(60), Decimal(0), progress)
        progress = {
            key: values[key]
            for key in ("pallets_remaining", "total_pallets_completed", "potential_overrun_pallets")
        }

    # 8 x 1.1 = 8.8 exactly; a float accumulator would give 8.800000000000002.
    assert progress["total_pallets_completed"] == Decimal("8.8")
    assert progress["pallets_remaining"] == Decimal("1.2")
    assert progress["potential_overrun_pallets"] == Decimal(0)


def test_pallets_beyond_remaining_become_potential_overrun_like_the_cli():
    values = calc.hourly_update_values(
        CONFIG, Decimal("3.75"), Decimal(60), Decimal(0), fresh_progress(remaining=Decimal("2.5"))
    )
    assert values["pallets_remaining"] == Decimal(0)
    assert values["total_pallets_completed"] == Decimal("2.5")
    assert values["potential_overrun_pallets"] == Decimal("1.25")


def test_expected_output_follows_actual_elapsed_minutes():
    values = calc.hourly_update_values(CONFIG, Decimal(1), Decimal(75), Decimal(0), fresh_progress())
    assert values["expected_packs"] == Decimal("630.0000")


def test_negative_pallets_rejected():
    with pytest.raises(ValueError):
        calc.hourly_update_values(CONFIG, Decimal("-0.5"), Decimal(60), Decimal(0), fresh_progress())


def test_zero_length_period_rejected():
    with pytest.raises(ValueError):
        calc.hourly_update_values(CONFIG, Decimal(1), Decimal(0), Decimal(0), fresh_progress())


@pytest.mark.parametrize("field", ["target_speed_ppm", "packs_per_case", "cases_per_pallet", "pack_weight_kg"])
@pytest.mark.parametrize("bad", [Decimal(0), Decimal(-1)])
def test_pack_config_rejects_non_positive_values(field, bad):
    values = {
        "target_speed_ppm": Decimal(1),
        "packs_per_case": Decimal(1),
        "cases_per_pallet": Decimal(1),
        "pack_weight_kg": Decimal(1),
        field: bad,
    }
    with pytest.raises(ValueError):
        calc.PackConfig(**values)


# ==========================================================
# OUTPUT TOTALS
# ==========================================================


def test_output_totals_gap_and_achievement():
    totals = calc.OutputTotals()
    totals.add_period(CONFIG, Decimal(504), Decimal("3.75"))
    totals.add_period(CONFIG, Decimal(504), Decimal("5.04"))

    api = totals.to_api()
    assert api["expected_pallets"] == 10.08
    assert api["actual_pallets"] == 8.79
    assert api["output_gap_pallets"] == 1.29
    assert api["output_gap_tonnes"] == 0.129
    assert api["production_achievement_percent"] == 87.2
    assert "oee" not in " ".join(api.keys()).lower()


def test_zero_expected_output_gives_null_achievement_not_zero():
    totals = calc.OutputTotals()
    assert totals.achievement_percent is None
    assert totals.to_api()["production_achievement_percent"] is None
    assert totals.to_api()["output_gap_tonnes"] == 0.0


def test_over_performance_never_produces_a_negative_gap():
    totals = calc.OutputTotals()
    totals.add_period(CONFIG, Decimal(504), Decimal(6))
    assert totals.gap_packs == 0
    assert totals.achievement_percent > 100


def test_mixed_pack_sizes_combine_by_tonnes():
    totals = calc.OutputTotals()
    totals.add_period(CONFIG, Decimal(100), Decimal(1))  # 0.1 t expected, 0.1 t actual
    totals.add_period(ROVEMA, Decimal(1760), Decimal("0.5"))  # 1.76 t expected, 0.88 t actual
    assert totals.to_api()["production_achievement_percent"] == 52.7


def test_as_number_rounds_half_up_at_the_boundary_only():
    assert calc.as_number(Decimal("2.345"), calc.TONNES_PLACES) == 2.345
    assert calc.as_number(Decimal("2.3455"), calc.TONNES_PLACES) == 2.346
    assert calc.as_number(Decimal("0.05"), calc.PERCENT_PLACES) == 0.1
    assert calc.as_number(None, calc.PERCENT_PLACES) is None


# ==========================================================
# X-RAY WASTE
# ==========================================================


def test_xray_waste_estimate_when_count_available():
    result = calc.xray_waste(Decimal(1000), Decimal(950))
    assert result["waste_status"] == "estimated"
    assert result["post_xray_pack_difference"] == Decimal(50)
    assert result["estimated_post_xray_waste_percent"] == Decimal(5)


def test_xray_count_below_palletised_output_is_a_data_quality_warning_not_zero():
    result = calc.xray_waste(Decimal(900), Decimal(950))
    assert result["waste_status"] == "data_quality_warning"
    assert result["post_xray_pack_difference"] == Decimal(-50)
    assert result["estimated_post_xray_waste_percent"] is None
    # Names both recorded figures and the shortfall, and says why this is
    # impossible - not just "check the numbers".
    assert "900" in result["warning"] and "950" in result["warning"]
    assert "50" in result["warning"]
    assert "lower than" in result["warning"]


# ----------------------------------------------------------
# X-ray waste direction
# ----------------------------------------------------------


def test_difference_is_xray_minus_palletised_not_the_other_way_round():
    """Packs pass the X-ray BEFORE they are palletised, so a healthy run
    has more X-ray packs than palletised packs."""
    result = calc.xray_waste(Decimal(11200), Decimal(11000))

    assert result["waste_status"] == "estimated"
    assert result["post_xray_pack_difference"] == Decimal(200)
    assert calc.as_number(result["estimated_post_xray_waste_percent"], calc.PERCENT_PLACES) == 1.8


def test_equal_counts_are_zero_waste_not_a_warning():
    result = calc.xray_waste(Decimal(11000), Decimal(11000))

    assert result["waste_status"] == "estimated"
    assert result["post_xray_pack_difference"] == Decimal(0)
    assert result["estimated_post_xray_waste_percent"] == Decimal(0)
    assert result["warning"] is None


@pytest.mark.parametrize(
    "count, palletised, expected_percent",
    [
        (Decimal(10000), Decimal(9900), Decimal(1)),
        (Decimal(5000), Decimal(4000), Decimal(20)),
        (Decimal(11200), Decimal(11000), Decimal(200) / Decimal(11200) * Decimal(100)),
    ],
)
def test_exact_percentage_is_difference_over_the_xray_count(count, palletised, expected_percent):
    result = calc.xray_waste(count, palletised)
    assert result["estimated_post_xray_waste_percent"] == expected_percent


def test_a_shortfall_is_never_presented_as_ordinary_waste():
    """No abs(), no clamp to zero and no percentage - any of which would
    make a broken count look like a normal result."""
    result = calc.xray_waste(Decimal(10800), Decimal(11000))

    assert result["post_xray_pack_difference"] == Decimal(-200)
    assert result["post_xray_pack_difference"] != Decimal(200)
    assert result["post_xray_pack_difference"] != Decimal(0)
    assert result["estimated_post_xray_waste_percent"] is None
    assert result["waste_status"] != "estimated"


def test_completion_summary_carries_a_shortfall_through_with_decimal_final_pallets():
    config = calc.PackConfig(Decimal(120), Decimal(8), Decimal(220), Decimal(1))

    # 5 covered + 1.25 final = 6.25 pallets x 220 cases x 8 packs = 11000.
    summary = calc.completion_summary(
        config, Decimal("6.25"), Decimal(5), Decimal("1.25"), True, Decimal(10800)
    )

    assert summary["palletised_pallets"] == Decimal("6.25")
    assert summary["palletised_packs"] == Decimal(11000)
    assert summary["waste_status"] == "data_quality_warning"
    assert summary["post_xray_pack_difference"] == Decimal(-200)
    assert summary["estimated_post_xray_waste_percent"] is None


def test_completion_summary_with_decimal_final_pallets_and_a_valid_count():
    config = calc.PackConfig(Decimal(120), Decimal(8), Decimal(220), Decimal(1))

    summary = calc.completion_summary(
        config, Decimal("6.25"), Decimal(5), Decimal("1.25"), True, Decimal(11200)
    )

    assert summary["palletised_packs"] == Decimal(11000)
    assert summary["waste_status"] == "estimated"
    assert summary["post_xray_pack_difference"] == Decimal(200)
    assert calc.as_number(summary["estimated_post_xray_waste_percent"], calc.PERCENT_PLACES) == 1.8


def test_zero_xray_count_with_no_output_has_no_percentage():
    result = calc.xray_waste(Decimal(0), Decimal(0))
    assert result["waste_status"] == "no_output"
    assert result["estimated_post_xray_waste_percent"] is None


@pytest.mark.parametrize("count, palletised", [(-1, 0), (10, -1), (None, 0)])
def test_xray_waste_rejects_impossible_inputs(count, palletised):
    with pytest.raises(ValueError):
        calc.xray_waste(count, palletised)


# ==========================================================
# INTERVALS
# ==========================================================


def test_merge_overlapping_and_touching_intervals():
    merged = calc.merge_intervals(
        [
            (utc(2026, 1, 1, 9), utc(2026, 1, 1, 10)),
            (utc(2026, 1, 1, 9, 30), utc(2026, 1, 1, 11)),
            (utc(2026, 1, 1, 11), utc(2026, 1, 1, 11, 15)),
            (utc(2026, 1, 1, 12), utc(2026, 1, 1, 12, 5)),
        ]
    )
    assert merged == [
        (utc(2026, 1, 1, 9), utc(2026, 1, 1, 11, 15)),
        (utc(2026, 1, 1, 12), utc(2026, 1, 1, 12, 5)),
    ]
    assert calc.total_minutes(merged) == Decimal(140)


def test_subtract_and_intersect_intervals():
    base = [(utc(2026, 1, 1, 9), utc(2026, 1, 1, 10))]
    cut = [(utc(2026, 1, 1, 9, 20), utc(2026, 1, 1, 9, 40))]
    assert calc.total_minutes(calc.subtract_intervals(base, cut)) == Decimal(40)
    assert calc.total_minutes(calc.intersect_intervals(base, cut)) == Decimal(20)


# ==========================================================
# GAP ATTRIBUTION
# ==========================================================

WINDOW_START = utc(2026, 1, 12, 6)
WINDOW_END = utc(2026, 1, 12, 14)
RUN_START = utc(2026, 1, 12, 6)
RUN_END = utc(2026, 1, 12, 14)


def period(start_hour, end_hour, expected, pallets, reason=False):
    return {
        "start": utc(2026, 1, 12, start_hour),
        "end": utc(2026, 1, 12, end_hour),
        "expected_packs": Decimal(expected),
        "actual_pallets": Decimal(pallets),
        "loss_reason_recorded": reason,
    }


def attribute(periods, planned=(), faults=(), window=(WINDOW_START, WINDOW_END), run=(RUN_START, RUN_END)):
    return calc.attribute_run_gap(CONFIG, periods, list(planned), list(faults), *window, *run)


def test_planned_and_unplanned_downtime_converted_at_target_rate():
    # 60-min period, expected 504, actual 2 pallets = 200 packs -> gap 304.
    result = attribute(
        [period(6, 7, 504, 2)],
        planned=[{"start": utc(2026, 1, 12, 6, 0), "end": utc(2026, 1, 12, 6, 10), "reason": "Film Change"}],
        faults=[{"start": utc(2026, 1, 12, 6, 20), "end": utc(2026, 1, 12, 6, 40), "machine": "BV1"}],
    )

    assert result.measured_gap.packs == Decimal(304)
    assert result.planned_downtime.minutes == Decimal(10)
    assert result.planned_downtime.packs == Decimal(84)  # 10 x 8.4
    assert result.unplanned_downtime.minutes == Decimal(20)
    assert result.unplanned_downtime.packs == Decimal(168)  # 20 x 8.4
    assert result.unexplained_gap.packs == Decimal(52)
    assert result.planned_downtime.tonnes == Decimal("0.084")


def test_overlapping_faults_are_not_double_counted():
    result = attribute(
        [period(6, 7, 504, 0)],
        faults=[
            {"start": utc(2026, 1, 12, 6, 0), "end": utc(2026, 1, 12, 6, 30), "machine": "BV1"},
            {"start": utc(2026, 1, 12, 6, 15), "end": utc(2026, 1, 12, 6, 45), "machine": "Casepacker"},
        ],
    )
    assert result.unplanned_downtime.minutes == Decimal(45)
    assert result.unplanned_downtime.packs == Decimal(378)
    # Per-machine shares always sum back to the capped unplanned total.
    assert sum(b.packs for b in result.by_machine.values()) == result.unplanned_downtime.packs


def test_fault_time_inside_planned_downtime_counts_once_as_planned():
    result = attribute(
        [period(6, 7, 504, 0)],
        planned=[{"start": utc(2026, 1, 12, 6, 0), "end": utc(2026, 1, 12, 6, 30), "reason": "CCP Check"}],
        faults=[{"start": utc(2026, 1, 12, 6, 20), "end": utc(2026, 1, 12, 6, 40), "machine": "BV1"}],
    )
    assert result.planned_downtime.minutes == Decimal(30)
    assert result.unplanned_downtime.minutes == Decimal(10)


def test_attribution_is_capped_at_the_measured_gap():
    # Gap only 50 packs, but 60 minutes of downtime would explain 504.
    result = attribute(
        [period(6, 7, 504, "4.54")],
        planned=[{"start": utc(2026, 1, 12, 6, 0), "end": utc(2026, 1, 12, 6, 30), "reason": "Changeover"}],
        faults=[{"start": utc(2026, 1, 12, 6, 30), "end": utc(2026, 1, 12, 7, 0), "machine": "BV1"}],
    )
    assert result.measured_gap.packs == Decimal(50)
    assert result.planned_downtime.packs == Decimal(50)
    assert result.unplanned_downtime.packs == Decimal(0)
    assert result.unexplained_gap.packs == Decimal(0)
    # The uncapped potential stays visible for context.
    assert result.planned_downtime_uncapped.packs == Decimal(252)
    assert result.unplanned_downtime_uncapped.packs == Decimal(252)


def test_unexplained_remainder_is_preserved_and_split_by_recorded_reasons():
    result = attribute(
        [period(6, 7, 504, 4, reason=True), period(7, 8, 504, 4, reason=False)],
    )
    assert result.measured_gap.packs == Decimal(208)
    assert result.other_or_speed_loss.packs == Decimal(104)
    assert result.unexplained_gap.packs == Decimal(104)
    total = (
        result.planned_downtime.packs + result.unplanned_downtime.packs
        + result.other_or_speed_loss.packs + result.unexplained_gap.packs
    )
    assert total == result.measured_gap.packs


def test_downtime_outside_the_window_or_run_is_not_counted():
    result = attribute(
        [period(6, 7, 504, 0)],
        faults=[{"start": utc(2026, 1, 12, 5, 0), "end": utc(2026, 1, 12, 6, 10), "machine": "BV1"}],
        run=(utc(2026, 1, 12, 6, 5), RUN_END),
    )
    # Only 06:05-06:10 is inside both the run and its reported period.
    assert result.unplanned_downtime.minutes == Decimal(5)


def test_downtime_outside_reported_hourly_periods_is_not_counted():
    result = attribute(
        [period(6, 7, 504, 0)],
        faults=[{"start": utc(2026, 1, 12, 8, 0), "end": utc(2026, 1, 12, 9, 0), "machine": "BV1"}],
    )
    assert result.unplanned_downtime.minutes == Decimal(0)


def test_no_periods_means_no_attribution():
    result = attribute([], faults=[{"start": WINDOW_START, "end": WINDOW_END, "machine": "BV1"}])
    assert result.measured_gap.packs == 0
    assert result.unplanned_downtime.minutes == 0


def test_attribution_api_is_labelled_estimated_and_ranks_by_tonnes():
    result = attribute(
        [period(6, 7, 504, 0)],
        faults=[
            {"start": utc(2026, 1, 12, 6, 0), "end": utc(2026, 1, 12, 6, 5), "machine": "Small"},
            {"start": utc(2026, 1, 12, 6, 10), "end": utc(2026, 1, 12, 6, 50), "machine": "Big"},
        ],
    )
    api = result.to_api()
    assert api["calculation_status"] == "estimated"
    assert "capped" in api["method"]
    assert [m["machine"] for m in api["by_machine"]] == ["Big", "Small"]
    assert set(api["unplanned_downtime"]) == {
        "minutes", "estimated_lost_packs", "estimated_lost_pallets", "estimated_lost_tonnes",
    }


# ==========================================================
# ESTIMATED OEE
# ==========================================================


def test_estimated_oee_when_every_input_is_captured():
    result = calc.estimate_oee(
        period_minutes=480, planned_minutes=30, unplanned_minutes=45,
        effective_output_minutes=360, quality_palletised_packs=9500, quality_xray_packs=10000,
    )
    assert result["calculation_status"] == "estimated"
    assert result["availability_percent"] == 90.0     # 405 / 450
    assert result["performance_percent"] == 88.9      # 360 / 405
    assert result["estimated_quality_percent"] == 95.0
    assert result["estimated_oee_percent"] == 76.0    # 0.9 x 0.8889 x 0.95


def test_estimated_oee_never_assumes_quality():
    result = calc.estimate_oee(480, 30, 45, 360)
    assert result["calculation_status"] == "partial"
    assert result["availability_percent"] == 90.0
    assert result["estimated_quality_percent"] is None
    assert result["estimated_oee_percent"] is None
    assert "never assumed" in result["unavailable_reason"]


def test_estimated_oee_rejects_impossible_quality_inputs():
    result = calc.estimate_oee(480, 0, 0, 400, quality_palletised_packs=11000, quality_xray_packs=10000)
    assert result["estimated_oee_percent"] is None
    assert result["calculation_status"] == "partial"


def test_estimated_oee_unavailable_without_production_time():
    result = calc.estimate_oee(0, 0, 0, 0)
    assert result["calculation_status"] == "unavailable"
    assert result["availability_percent"] is None
    assert result["unavailable_reason"]


def test_estimated_oee_partial_when_downtime_consumes_all_run_time():
    result = calc.estimate_oee(60, 0, 60, 0)
    assert result["availability_percent"] == 0.0
    assert result["performance_percent"] is None
    assert result["calculation_status"] == "partial"


# ==========================================================
# WEEKLY TARGET PACE
# ==========================================================

WEEK = week_window_starting(date(2026, 1, 12))  # Mon 12 Jan 06:00 GMT


def test_on_pace_is_green_even_though_far_from_final_target():
    # Halfway through the week, 50.1 of 100 t done -> on pace.
    now = WEEK.start + (WEEK.end - WEEK.start) / 2
    result = calc.weekly_target_progress(Decimal(100), Decimal("50.1"), WEEK, now, has_data=True)
    assert result["target_status"] == "green"
    assert result["percent_complete"] == 50.1
    assert result["expected_tonnes_by_now"] == 50.0
    assert result["tonnes_remaining"] == 49.9


def test_behind_pace_is_red():
    now = WEEK.start + (WEEK.end - WEEK.start) * 3 / 4
    result = calc.weekly_target_progress(Decimal(100), Decimal(60), WEEK, now, has_data=True)
    assert result["target_status"] == "red"
    assert result["expected_tonnes_by_now"] == 75.0


def test_early_week_low_percentage_can_still_be_green():
    now = WEEK.start + timedelta(hours=6)
    result = calc.weekly_target_progress(Decimal(168), Decimal(7), WEEK, now, has_data=True)
    assert result["percent_complete"] == 4.2
    assert result["target_status"] == "green"


def test_no_target_is_grey():
    result = calc.weekly_target_progress(None, Decimal(10), WEEK, WEEK.start + timedelta(days=1), has_data=True)
    assert result["target_status"] == "grey"
    assert result["tonnes_remaining"] is None


def test_no_data_is_grey_even_with_a_target():
    result = calc.weekly_target_progress(
        Decimal(100), Decimal(0), WEEK, WEEK.start + timedelta(days=1), has_data=False
    )
    assert result["target_status"] == "grey"
    assert result["expected_tonnes_by_now"] is not None


# ==========================================================
# ATTENTION AND FRESHNESS
# ==========================================================


@pytest.mark.parametrize(
    "achievement, open_faults, expected",
    [
        (Decimal("99"), 1, "red"),
        (Decimal("84.99"), 0, "red"),
        (Decimal("85"), 0, "amber"),
        (Decimal("94.99"), 0, "amber"),
        (Decimal("95"), 0, "green"),
        (Decimal("120"), 0, "green"),
        (None, 0, "grey"),
        (None, 2, "red"),
    ],
)
def test_line_attention_thresholds(achievement, open_faults, expected):
    status, explanation = calc.line_attention(achievement, open_faults)
    assert status == expected
    assert explanation


def test_freshness_current_stale_and_no_active_run():
    now = utc(2026, 1, 12, 12)

    current = calc.freshness(True, now - timedelta(minutes=30), utc(2026, 1, 12, 6), now)
    stale = calc.freshness(True, now - timedelta(minutes=90), utc(2026, 1, 12, 6), now)
    never = calc.freshness(True, None, now - timedelta(minutes=80), now)
    idle = calc.freshness(False, None, None, now)

    assert current["stale_status"] == "current"
    assert current["minutes_since_last_hourly_update"] == 30.0
    assert stale["stale_status"] == "stale"
    assert "90.0 minutes" in stale["stale_reason"]
    assert never["stale_status"] == "stale"
    assert "since the run started" in never["stale_reason"]
    assert idle["stale_status"] == "no_active_run"


def test_latest_ignores_missing_timestamps():
    assert calc.latest(None, utc(2026, 1, 1), None, utc(2026, 1, 2)) == utc(2026, 1, 2)
    assert calc.latest(None, None) is None


def test_duration_minutes_rejects_end_before_start():
    with pytest.raises(ValueError):
        calc.duration_minutes(utc(2026, 1, 1, 10), utc(2026, 1, 1, 9))
    assert calc.duration_minutes(utc(2026, 1, 1, 9), utc(2026, 1, 1, 9, 42, 30)) == Decimal("42.5")
