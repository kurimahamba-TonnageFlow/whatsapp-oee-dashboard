# ==========================================================
# TONNAGEFLOW PULSE
# Factory time (Europe/London)
# ==========================================================
#
# Pure, side-effect-free. Every factory boundary (shift, factory day,
# production week) is defined in Europe/London wall-clock time and
# converted to an aware UTC datetime, so GMT/BST changes are handled by
# the tz database rather than by fixed offsets:
#   - Day 06:00-14:00, Afternoon 14:00-22:00, Night 22:00-06:00.
#   - Factory day: 06:00 until 06:00 the next day.
#   - Production week: Monday 06:00 until the following Monday 06:00.
# None of these boundaries fall inside the UK's 01:00-02:00 transition
# hour, so they are never ambiguous or non-existent. A Night shift that
# spans a clock change is genuinely 7 or 9 hours long, and is reported
# as such.

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

FACTORY_TIMEZONE_NAME = "Europe/London"
FACTORY_TZ = ZoneInfo(FACTORY_TIMEZONE_NAME)

DAY_START_HOUR = 6

# (name, start hour, end hour) in London local time.
SHIFTS = (
    ("Day", 6, 14),
    ("Afternoon", 14, 22),
    ("Night", 22, 6),
)

SHIFT_NAMES = tuple(name for name, _start, _end in SHIFTS)

WINDOW_KINDS = (
    "current_shift",
    "factory_day",
    "production_week",
    "rolling_24h",
)

# Windows whose hourly output is selected by each update's operational
# shift instance (see operational_shift_window) rather than by raw
# period-end time. Every shift instance starts at 06:00, 14:00 or 22:00,
# so it falls cleanly inside exactly one shift, factory day and week.
SHIFT_BASED_WINDOW_KINDS = frozenset({"current_shift", "factory_day", "production_week"})


@dataclass(frozen=True)
class TimeWindow:
    kind: str
    label: str
    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def to_api(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "timezone": FACTORY_TIMEZONE_NAME,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "start_local": self.start.astimezone(FACTORY_TZ).isoformat(),
            "end_local": self.end.astimezone(FACTORY_TZ).isoformat(),
        }


def _require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Factory time calculations require a timezone-aware datetime.")
    return moment


def _london(day: date, hour: int) -> datetime:
    """London wall-clock day+hour as an aware UTC datetime."""
    local = datetime.combine(day, time(hour=hour), tzinfo=FACTORY_TZ)
    return local.astimezone(timezone.utc)


def to_london(moment: datetime) -> datetime:
    return _require_aware(moment).astimezone(FACTORY_TZ)


def shift_name_at(moment: datetime) -> str:
    hour = to_london(moment).hour

    if 6 <= hour < 14:
        return "Day"
    if 14 <= hour < 22:
        return "Afternoon"
    return "Night"


def shift_window_for(shift_date: date, shift_name: str) -> TimeWindow:
    """Shift that STARTS on shift_date (a Night shift starting on the
    evening of shift_date ends at 06:00 the following morning)."""
    for name, start_hour, end_hour in SHIFTS:
        if name == shift_name:
            end_date = shift_date + timedelta(days=1) if end_hour <= start_hour else shift_date
            return TimeWindow(
                kind="current_shift",
                label=f"{name} shift {shift_date.isoformat()}",
                start=_london(shift_date, start_hour),
                end=_london(end_date, end_hour),
            )

    raise ValueError(f"Unknown shift '{shift_name}'.")


_SHIFT_ALIASES = {
    "day": "Day",
    "days": "Day",
    "afternoon": "Afternoon",
    "afternoons": "Afternoon",
    "night": "Night",
    "nights": "Night",
}


def normalise_shift_name(label) -> str | None:
    """Maps the shift label a run was started with ('Days', 'Afternoons',
    'Nights' from the React HMI, or 'Day'/'Afternoon'/'Night') to the
    canonical factory shift name. None for anything unrecognised."""
    if not isinstance(label, str):
        return None
    return _SHIFT_ALIASES.get(label.strip().lower())


def operational_shift_window(shift_name: str, period_end: datetime) -> TimeWindow:
    """The instance of the run's recorded shift that an hourly period
    belongs to: the latest instance of that named shift starting at or
    before the period's END. A period ending exactly at 06:00, 14:00 or
    22:00 therefore stays with the shift that produced it, and a period
    crossing a boundary stays with the run's recorded shift instead of
    moving to the next one."""
    local_date = to_london(period_end).date()
    candidates = [
        shift_window_for(local_date - timedelta(days=offset), shift_name)
        for offset in (0, 1)
    ]
    eligible = [window for window in candidates if window.start <= period_end]
    return max(eligible, key=lambda window: window.start)


def current_shift_window(now: datetime) -> TimeWindow:
    local = to_london(now)
    name = shift_name_at(now)

    if name == "Night" and local.hour < DAY_START_HOUR:
        shift_date = local.date() - timedelta(days=1)
    else:
        shift_date = local.date()

    return shift_window_for(shift_date, name)


def factory_date_of(moment: datetime) -> date:
    """The factory day (06:00-06:00 London) a moment belongs to."""
    local = to_london(moment)
    if local.hour < DAY_START_HOUR:
        return local.date() - timedelta(days=1)
    return local.date()


def factory_day_start(day: date) -> datetime:
    """06:00 London on `day`, as aware UTC."""
    return _london(day, DAY_START_HOUR)


def factory_day_window(now: datetime) -> TimeWindow:
    day = factory_date_of(now)
    return TimeWindow(
        kind="factory_day",
        label=f"Factory day {day.isoformat()}",
        start=_london(day, DAY_START_HOUR),
        end=_london(day + timedelta(days=1), DAY_START_HOUR),
    )


def production_week_start_date(moment: datetime) -> date:
    day = factory_date_of(moment)
    return day - timedelta(days=day.weekday())


def week_window_starting(monday: date) -> TimeWindow:
    if monday.weekday() != 0:
        raise ValueError("A production week must start on a Monday.")

    return TimeWindow(
        kind="production_week",
        label=f"Production week from {monday.isoformat()}",
        start=_london(monday, DAY_START_HOUR),
        end=_london(monday + timedelta(days=7), DAY_START_HOUR),
    )


def production_week_window(now: datetime) -> TimeWindow:
    return week_window_starting(production_week_start_date(now))


def rolling_24h_window(now: datetime) -> TimeWindow:
    end = _require_aware(now).astimezone(timezone.utc)
    return TimeWindow(
        kind="rolling_24h",
        label="Previous 24 hours",
        start=end - timedelta(hours=24),
        end=end,
    )


def resolve_window(kind: str, now: datetime) -> TimeWindow:
    if kind == "current_shift":
        return current_shift_window(now)
    if kind == "factory_day":
        return factory_day_window(now)
    if kind == "production_week":
        return production_week_window(now)
    if kind == "rolling_24h":
        return rolling_24h_window(now)

    raise ValueError(f"Unknown window '{kind}'.")


def timedelta_seconds(delta: timedelta) -> Decimal:
    """Exact seconds (microsecond precision) as a Decimal - avoids the
    binary-float rounding of timedelta.total_seconds()."""
    return (
        Decimal(delta.days) * 86400
        + Decimal(delta.seconds)
        + Decimal(delta.microseconds) / Decimal(1_000_000)
    )


def elapsed_fraction(window: TimeWindow, now: datetime) -> Decimal:
    """0 before the window starts, 1 once it has ended."""
    total = timedelta_seconds(window.end - window.start)
    elapsed = timedelta_seconds(_require_aware(now) - window.start)

    if total <= 0:
        return Decimal(1)

    return min(max(elapsed / total, Decimal(0)), Decimal(1))
