"""
Offline tests for src/factory_time.py - Europe/London factory shifts,
factory days, production weeks and rolling windows, across GMT and BST.
Pure functions only: no database, network or real clock.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src import factory_time as ft


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ==========================================================
# SHIFTS
# ==========================================================


@pytest.mark.parametrize(
    "moment, expected",
    [
        # January = GMT (London == UTC)
        (utc(2026, 1, 12, 6, 0), "Day"),
        (utc(2026, 1, 12, 13, 59), "Day"),
        (utc(2026, 1, 12, 14, 0), "Afternoon"),
        (utc(2026, 1, 12, 21, 59), "Afternoon"),
        (utc(2026, 1, 12, 22, 0), "Night"),
        (utc(2026, 1, 13, 5, 59), "Night"),
        # July = BST (London == UTC+1): 05:00 UTC is 06:00 London
        (utc(2026, 7, 13, 5, 0), "Day"),
        (utc(2026, 7, 13, 4, 59), "Night"),
        (utc(2026, 7, 13, 13, 0), "Afternoon"),
        (utc(2026, 7, 13, 21, 0), "Night"),
    ],
)
def test_shift_name_uses_london_wall_clock(moment, expected):
    assert ft.shift_name_at(moment) == expected


def test_current_day_shift_window_in_gmt():
    window = ft.current_shift_window(utc(2026, 1, 12, 9, 30))
    assert window.start == utc(2026, 1, 12, 6, 0)
    assert window.end == utc(2026, 1, 12, 14, 0)


def test_current_day_shift_window_in_bst_is_one_hour_earlier_in_utc():
    window = ft.current_shift_window(utc(2026, 7, 13, 9, 30))
    assert window.start == utc(2026, 7, 13, 5, 0)
    assert window.end == utc(2026, 7, 13, 13, 0)


def test_night_shift_after_midnight_belongs_to_previous_evening():
    window = ft.current_shift_window(utc(2026, 1, 13, 3, 0))
    assert window.label == "Night shift 2026-01-12"
    assert window.start == utc(2026, 1, 12, 22, 0)
    assert window.end == utc(2026, 1, 13, 6, 0)


def test_night_shift_across_spring_clock_change_is_seven_hours():
    # Clocks go forward 01:00 UTC on Sunday 29 March 2026.
    window = ft.current_shift_window(utc(2026, 3, 29, 3, 0))
    assert window.start == utc(2026, 3, 28, 22, 0)
    assert window.end == utc(2026, 3, 29, 5, 0)
    assert window.end - window.start == timedelta(hours=7)


def test_night_shift_across_autumn_clock_change_is_nine_hours():
    # Clocks go back 01:00 UTC on Sunday 25 October 2026.
    window = ft.current_shift_window(utc(2026, 10, 25, 3, 0))
    assert window.start == utc(2026, 10, 24, 21, 0)
    assert window.end == utc(2026, 10, 25, 6, 0)
    assert window.end - window.start == timedelta(hours=9)


def test_unknown_shift_name_rejected():
    with pytest.raises(ValueError):
        ft.shift_window_for(date(2026, 1, 12), "Graveyard")


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        ft.current_shift_window(datetime(2026, 1, 12, 9, 0))


# ==========================================================
# FACTORY DAY
# ==========================================================


def test_factory_day_runs_0600_to_0600_london():
    window = ft.factory_day_window(utc(2026, 7, 14, 3, 0))  # 04:00 BST
    assert window.label == "Factory day 2026-07-13"
    assert window.start == utc(2026, 7, 13, 5, 0)
    assert window.end == utc(2026, 7, 14, 5, 0)


def test_factory_day_start_helper_matches_window():
    assert ft.factory_day_start(date(2026, 1, 12)) == utc(2026, 1, 12, 6, 0)
    assert ft.factory_day_start(date(2026, 7, 13)) == utc(2026, 7, 13, 5, 0)


# ==========================================================
# PRODUCTION WEEK (Monday 06:00 London -> Monday 06:00 London)
# ==========================================================


def test_week_starts_monday_0600_gmt():
    window = ft.production_week_window(utc(2026, 1, 14, 12, 0))  # Wednesday
    assert window.start == utc(2026, 1, 12, 6, 0)
    assert window.end == utc(2026, 1, 19, 6, 0)


def test_week_starts_monday_0600_bst():
    window = ft.production_week_window(utc(2026, 7, 15, 12, 0))
    assert window.start == utc(2026, 7, 13, 5, 0)
    assert window.end == utc(2026, 7, 20, 5, 0)


def test_monday_before_0600_london_still_belongs_to_previous_week():
    # 05:59 London on Monday 13 July (BST) = 04:59 UTC.
    window = ft.production_week_window(utc(2026, 7, 13, 4, 59))
    assert window.start == utc(2026, 7, 6, 5, 0)


def test_monday_exactly_0600_london_starts_the_new_week():
    window = ft.production_week_window(utc(2026, 7, 13, 5, 0))
    assert window.start == utc(2026, 7, 13, 5, 0)


def test_week_spanning_clock_change_is_167_hours():
    window = ft.week_window_starting(date(2026, 3, 23))
    assert window.start == utc(2026, 3, 23, 6, 0)
    assert window.end == utc(2026, 3, 30, 5, 0)
    assert window.end - window.start == timedelta(hours=167)


def test_week_must_start_on_monday():
    with pytest.raises(ValueError):
        ft.week_window_starting(date(2026, 7, 14))


# ==========================================================
# ROLLING 24 HOURS AND RESOLVER
# ==========================================================


def test_rolling_24h_is_exactly_24_hours_ending_now():
    now = utc(2026, 3, 29, 12, 0)
    window = ft.rolling_24h_window(now)
    assert window.end == now
    assert window.start == utc(2026, 3, 28, 12, 0)


@pytest.mark.parametrize("kind", ft.WINDOW_KINDS)
def test_resolve_window_supports_every_kind(kind):
    window = ft.resolve_window(kind, utc(2026, 7, 15, 12, 0))
    assert window.kind == kind
    assert window.start < window.end
    assert window.to_api()["timezone"] == "Europe/London"


def test_resolve_window_rejects_unknown_kind():
    with pytest.raises(ValueError):
        ft.resolve_window("fortnight", utc(2026, 7, 15, 12, 0))


def test_elapsed_fraction_is_exact_decimal_and_clamped():
    week = ft.week_window_starting(date(2026, 1, 12))
    halfway = week.start + (week.end - week.start) / 2

    assert ft.elapsed_fraction(week, halfway) == Decimal("0.5")
    assert ft.elapsed_fraction(week, week.start - timedelta(days=1)) == Decimal(0)
    assert ft.elapsed_fraction(week, week.end + timedelta(days=1)) == Decimal(1)
