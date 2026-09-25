# ==========================================================
# TONNAGEFLOW PULSE
# Phase 1 calculations (the calculation authority)
# ==========================================================
#
# Pure and side-effect-free: no database, no network, no clock (the
# caller always passes `now`). Every manufacturing figure the HMI and
# management dashboard show is computed here, with decimal.Decimal
# end to end. Values are rounded ONLY when leaving the backend
# (as_number), ROUND_HALF_UP, to these places:
#   packs 2 dp, pallets 4 dp, tonnes 3 dp, minutes 1 dp, percent 1 dp.
#
# Vocabulary is deliberate:
#   - "Production achievement" = actual / expected output. It is NOT
#     OEE and is never labelled as such.
#   - "Estimated OEE" = Availability x Performance x Estimated Quality,
#     returned only when every factor comes from captured inputs;
#     otherwise null with an explicit unavailable reason.
#   - Every attribution of lost output to downtime is an ESTIMATE at
#     the run's own target rate, capped at the measured output gap.

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

try:
    from .factory_time import elapsed_fraction, timedelta_seconds
except ImportError:
    from factory_time import elapsed_fraction, timedelta_seconds


ZERO = Decimal(0)
SIXTY = Decimal(60)
HUNDRED = Decimal(100)
THOUSAND = Decimal(1000)

PACKS_PLACES = Decimal("0.01")
PALLETS_PLACES = Decimal("0.0001")
TONNES_PLACES = Decimal("0.001")
MINUTES_PLACES = Decimal("0.1")
PERCENT_PLACES = Decimal("0.1")

# Storage precision for the numeric(14,4) columns in migration 0003.
STORAGE_PLACES = Decimal("0.0001")

ACHIEVEMENT_GREEN_PERCENT = Decimal(95)
ACHIEVEMENT_AMBER_PERCENT = Decimal(85)

DEFAULT_STALE_AFTER_MINUTES = 75

ATTRIBUTION_METHOD = (
    "Estimated. Planned downtime and unplanned (fault) downtime are "
    "converted to lost packs at each run's own target speed (packs per "
    "minute x minutes), then to pallets and tonnes using that run's "
    "pack configuration. Only downtime inside both the run's reported "
    "hourly periods and the selected window is counted. Overlapping "
    "events are merged, and time covered by planned downtime is never "
    "counted again as unplanned. Planned is attributed first, then "
    "unplanned, and the total is capped at the measured output gap. "
    "The remainder is split into 'other or speed loss' (shortfall in "
    "hourly periods where the technician recorded a loss reason) and "
    "'unexplained gap'."
)


# ==========================================================
# DECIMAL HELPERS
# ==========================================================


def to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("Booleans are not numeric inputs.")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # repr() is the shortest round-tripping text, so 3.75 -> "3.75"
        # rather than the float's full binary expansion.
        return Decimal(repr(value))
    return Decimal(str(value))


def quantize(value, places: Decimal) -> Decimal | None:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return None
    return decimal_value.quantize(places, rounding=ROUND_HALF_UP)


def as_number(value, places: Decimal) -> float | None:
    """Final, outward-facing rounding. The float produced from a
    quantized Decimal prints exactly as the quantized value."""
    quantized = quantize(value, places)
    return None if quantized is None else float(quantized)


def for_storage(value) -> Decimal | None:
    return quantize(value, STORAGE_PLACES)


def minutes_between(start: datetime, end: datetime) -> Decimal:
    return timedelta_seconds(end - start) / SIXTY


def percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator is None or denominator <= 0:
        return None
    return numerator / denominator * HUNDRED


def duration_minutes(start: datetime, end: datetime | None) -> Decimal | None:
    if end is None:
        return None
    if end < start:
        raise ValueError("An end time cannot be earlier than its start time.")
    return minutes_between(start, end)


def latest(*moments):
    present = [m for m in moments if m is not None]
    return max(present) if present else None


# ==========================================================
# PACK CONFIGURATION AND CONVERSIONS
# ==========================================================


@dataclass(frozen=True)
class PackConfig:
    target_speed_ppm: Decimal
    packs_per_case: Decimal
    cases_per_pallet: Decimal
    pack_weight_kg: Decimal

    def __post_init__(self):
        for name in ("target_speed_ppm", "packs_per_case", "cases_per_pallet", "pack_weight_kg"):
            value = getattr(self, name)
            if value is None or value <= 0:
                raise ValueError(f"{name} must be greater than zero.")

    @classmethod
    def from_row(cls, row) -> "PackConfig":
        return cls(
            target_speed_ppm=to_decimal(row["target_speed_ppm"]),
            packs_per_case=to_decimal(row["packs_per_case"]),
            cases_per_pallet=to_decimal(row["cases_per_pallet"]),
            pack_weight_kg=to_decimal(row["pack_weight_kg"]),
        )

    @property
    def packs_per_pallet(self) -> Decimal:
        return self.packs_per_case * self.cases_per_pallet

    def pallets_to_packs(self, pallets) -> Decimal:
        return to_decimal(pallets) * self.packs_per_pallet

    def packs_to_pallets(self, packs) -> Decimal:
        return to_decimal(packs) / self.packs_per_pallet

    def packs_to_tonnes(self, packs) -> Decimal:
        return to_decimal(packs) * self.pack_weight_kg / THOUSAND

    def minutes_to_packs(self, minutes) -> Decimal:
        return to_decimal(minutes) * self.target_speed_ppm


# ==========================================================
# HOURLY UPDATE (write-time values)
# ==========================================================


def hourly_update_values(
    config: PackConfig,
    pallets_produced,
    period_minutes,
    planned_downtime_minutes,
    progress: dict,
) -> dict:
    """Values persisted for one hourly update. Expected output covers
    the actual elapsed period (target speed x period minutes), not a
    fixed 60 minutes. Run progress mirrors src/main.py's
    update_run_progress(): pallets reduce pallets_remaining until it
    reaches zero, anything beyond becomes potential overrun - but with
    exact Decimal arithmetic, so 3.75 + 3.75 + ... never drifts."""
    pallets = to_decimal(pallets_produced)
    minutes = to_decimal(period_minutes)

    if pallets < 0:
        raise ValueError("Pallets produced cannot be negative.")
    if minutes <= 0:
        raise ValueError("An hourly period must be longer than zero minutes.")

    expected_packs = config.minutes_to_packs(minutes)
    actual_packs = config.pallets_to_packs(pallets)
    lost_packs = max(expected_packs - actual_packs, ZERO)

    remaining = to_decimal(progress["pallets_remaining"]) or ZERO
    total_completed = to_decimal(progress["total_pallets_completed"]) or ZERO
    overrun = to_decimal(progress["potential_overrun_pallets"]) or ZERO

    if remaining <= 0:
        overrun += pallets
    else:
        planned_part = min(pallets, remaining)
        total_completed += planned_part
        remaining -= planned_part
        overrun += pallets - planned_part

    return {
        "pallets_completed": for_storage(pallets),
        "actual_pallets": for_storage(pallets),
        "expected_packs": for_storage(expected_packs),
        "actual_packs": for_storage(actual_packs),
        "expected_pallets": for_storage(config.packs_to_pallets(expected_packs)),
        "production_variance_packs": for_storage(actual_packs - expected_packs),
        "estimated_lost_packs": for_storage(lost_packs),
        "estimated_lost_minutes": for_storage(lost_packs / config.target_speed_ppm),
        "planned_downtime_minutes": for_storage(planned_downtime_minutes),
        "period_minutes": for_storage(minutes),
        "pallets_remaining": for_storage(remaining),
        "total_pallets_completed": for_storage(total_completed),
        "potential_overrun_pallets": for_storage(overrun),
    }


# ==========================================================
# OUTPUT SUMMARY (read-time)
# ==========================================================


@dataclass
class OutputTotals:
    expected_packs: Decimal = ZERO
    actual_packs: Decimal = ZERO
    expected_pallets: Decimal = ZERO
    actual_pallets: Decimal = ZERO
    expected_tonnes: Decimal = ZERO
    actual_tonnes: Decimal = ZERO
    hourly_update_count: int = 0

    def add_period(self, config: PackConfig, expected_packs, actual_pallets):
        expected = to_decimal(expected_packs)
        pallets = to_decimal(actual_pallets)
        actual = config.pallets_to_packs(pallets)

        self.expected_packs += expected
        self.actual_packs += actual
        self.expected_pallets += config.packs_to_pallets(expected)
        self.actual_pallets += pallets
        self.expected_tonnes += config.packs_to_tonnes(expected)
        self.actual_tonnes += config.packs_to_tonnes(actual)
        self.hourly_update_count += 1

    def merge(self, other: "OutputTotals"):
        self.expected_packs += other.expected_packs
        self.actual_packs += other.actual_packs
        self.expected_pallets += other.expected_pallets
        self.actual_pallets += other.actual_pallets
        self.expected_tonnes += other.expected_tonnes
        self.actual_tonnes += other.actual_tonnes
        self.hourly_update_count += other.hourly_update_count

    @property
    def gap_packs(self) -> Decimal:
        return max(self.expected_packs - self.actual_packs, ZERO)

    @property
    def gap_pallets(self) -> Decimal:
        return max(self.expected_pallets - self.actual_pallets, ZERO)

    @property
    def gap_tonnes(self) -> Decimal:
        return max(self.expected_tonnes - self.actual_tonnes, ZERO)

    @property
    def achievement_percent(self) -> Decimal | None:
        # Tonnes-weighted, so lines/products with different pack sizes
        # combine meaningfully. Identical to the packs ratio for one run.
        return percent(self.actual_tonnes, self.expected_tonnes)

    def to_api(self) -> dict:
        return {
            "expected_packs": as_number(self.expected_packs, PACKS_PLACES),
            "expected_pallets": as_number(self.expected_pallets, PALLETS_PLACES),
            "expected_tonnes": as_number(self.expected_tonnes, TONNES_PLACES),
            "actual_packs": as_number(self.actual_packs, PACKS_PLACES),
            "actual_pallets": as_number(self.actual_pallets, PALLETS_PLACES),
            "actual_tonnes": as_number(self.actual_tonnes, TONNES_PLACES),
            "output_gap_packs": as_number(self.gap_packs, PACKS_PLACES),
            "output_gap_pallets": as_number(self.gap_pallets, PALLETS_PLACES),
            "output_gap_tonnes": as_number(self.gap_tonnes, TONNES_PLACES),
            "production_achievement_percent": as_number(self.achievement_percent, PERCENT_PLACES),
            "hourly_update_count": self.hourly_update_count,
        }


# ==========================================================
# END-OF-SHIFT / RUN X-RAY WASTE (estimate)
# ==========================================================

XRAY_METHOD = (
    "Estimated post-X-ray waste = (X-ray pack count - palletised packs) "
    "/ X-ray pack count x 100, where palletised packs = pallets "
    "reported in the covered hourly updates x cases per pallet x packs "
    "per case. A Phase 1 ballpark only: it does not include rejects "
    "removed before the X-ray."
)


def xray_waste(xray_pack_count, palletised_packs) -> dict:
    """Post-X-ray waste is what the X-ray saw MINUS what reached a pallet:

        difference = X-ray packs - palletised packs
        waste %    = difference / X-ray packs x 100

    The direction matters. Packs pass the X-ray first and are palletised
    afterwards, so a healthy run has MORE X-ray packs than palletised
    packs, and the difference is the loss between those two points.

    A negative difference means more packs reached a pallet than the
    X-ray ever counted, which cannot physically happen: one of the two
    figures is wrong. It is returned as a data-quality warning with the
    SIGNED difference preserved - never abs(), never clamped to zero and
    never presented as an ordinary waste percentage.
    """
    count = to_decimal(xray_pack_count)
    palletised = to_decimal(palletised_packs)

    if count is None or count < 0 or palletised is None or palletised < 0:
        raise ValueError("X-ray count and palletised packs must be non-negative.")

    difference = count - palletised

    if difference < 0:
        return {
            "waste_status": "data_quality_warning",
            # Signed and un-clamped, so a reviewer sees the real
            # shortfall rather than a plausible-looking positive number.
            "post_xray_pack_difference": difference,
            "estimated_post_xray_waste_percent": None,
            "warning": (
                f"The X-ray pack count ({as_number(count, PACKS_PLACES)}) is lower than the "
                f"palletised packs already confirmed ({as_number(palletised, PACKS_PLACES)}), "
                f"a shortfall of {as_number(-difference, PACKS_PLACES)} packs. Packs are "
                "counted by the X-ray before they are palletised, so this cannot happen: "
                "either the X-ray count or a pallet figure is wrong. No waste figure has "
                "been calculated."
            ),
        }

    if count == 0:
        return {
            "waste_status": "no_output",
            "post_xray_pack_difference": difference,
            "estimated_post_xray_waste_percent": None,
            "warning": None,
        }

    return {
        "waste_status": "estimated",
        "post_xray_pack_difference": difference,
        "estimated_post_xray_waste_percent": difference / count * HUNDRED,
        "warning": None,
    }


def completion_summary(config, total_pallets, uncovered_pallets, final_pallets, count_available, xray_pack_count):
    """Preview of a Complete Run / end-of-shift capture, before anything
    is saved: every pallet recorded plus the declared final production,
    the palletised packs the X-ray count will be compared with, and the
    estimated waste (or why there is none)."""
    final = to_decimal(final_pallets) or ZERO
    if final < 0:
        raise ValueError("Final pallets cannot be negative.")

    palletised_pallets = to_decimal(uncovered_pallets) + final
    palletised_packs = config.pallets_to_packs(palletised_pallets)

    if count_available:
        waste = xray_waste(xray_pack_count, palletised_packs)
    else:
        waste = {
            "waste_status": "unavailable",
            "post_xray_pack_difference": None,
            "estimated_post_xray_waste_percent": None,
            "warning": None,
        }

    return {
        "total_pallets_recorded": to_decimal(total_pallets) + final,
        "final_pallets_produced": final,
        "palletised_pallets": palletised_pallets,
        "palletised_packs": palletised_packs,
        **waste,
    }


HOURLY_PROMPT_MINUTES_PAST_THE_HOUR = 10


def next_hourly_prompt_at(last_reported_at: datetime) -> datetime:
    """The hourly update prompt is due ten minutes after the next full
    hour following the last reported period end (or the run start).
    UK offsets are whole hours, so the UTC hour boundary is also the
    London hour boundary."""
    hour_start = last_reported_at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return hour_start + timedelta(hours=1, minutes=HOURLY_PROMPT_MINUTES_PAST_THE_HOUR)


# ==========================================================
# INTERVALS
# ==========================================================


def clip_interval(interval, lower: datetime, upper: datetime):
    start, end = interval
    start = max(start, lower)
    end = min(end, upper)
    return (start, end) if start < end else None


def merge_intervals(intervals):
    ordered = sorted((i for i in intervals if i is not None and i[0] < i[1]), key=lambda i: i[0])
    merged = []

    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return merged


def intersect_intervals(first, second):
    a = merge_intervals(first)
    b = merge_intervals(second)
    result = []
    i = j = 0

    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if start < end:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1

    return result


def subtract_intervals(base, removed):
    result = []
    removed = merge_intervals(removed)

    for start, end in merge_intervals(base):
        cursor = start
        for r_start, r_end in removed:
            if r_end <= cursor or r_start >= end:
                continue
            if r_start > cursor:
                result.append((cursor, r_start))
            cursor = max(cursor, r_end)
        if cursor < end:
            result.append((cursor, end))

    return result


def total_minutes(intervals) -> Decimal:
    return sum((minutes_between(s, e) for s, e in merge_intervals(intervals)), ZERO)


# ==========================================================
# GAP ATTRIBUTION (estimate)
# ==========================================================


@dataclass
class LossBucket:
    minutes: Decimal = ZERO
    packs: Decimal = ZERO
    pallets: Decimal = ZERO
    tonnes: Decimal = ZERO

    def add(self, config: PackConfig, packs: Decimal, minutes: Decimal = ZERO):
        self.minutes += minutes
        self.packs += packs
        self.pallets += config.packs_to_pallets(packs)
        self.tonnes += config.packs_to_tonnes(packs)

    def merge(self, other: "LossBucket"):
        self.minutes += other.minutes
        self.packs += other.packs
        self.pallets += other.pallets
        self.tonnes += other.tonnes

    def to_api(self, include_minutes=True) -> dict:
        data = {
            "estimated_lost_packs": as_number(self.packs, PACKS_PLACES),
            "estimated_lost_pallets": as_number(self.pallets, PALLETS_PLACES),
            "estimated_lost_tonnes": as_number(self.tonnes, TONNES_PLACES),
        }
        if include_minutes:
            data["minutes"] = as_number(self.minutes, MINUTES_PLACES)
        return data


_BUCKET_NAMES = (
    "measured_gap",
    "planned_downtime",
    "unplanned_downtime",
    "other_or_speed_loss",
    "unexplained_gap",
    "planned_downtime_uncapped",
    "unplanned_downtime_uncapped",
)


@dataclass
class GapAttribution:
    measured_gap: LossBucket
    planned_downtime: LossBucket
    unplanned_downtime: LossBucket
    other_or_speed_loss: LossBucket
    unexplained_gap: LossBucket
    planned_downtime_uncapped: LossBucket
    unplanned_downtime_uncapped: LossBucket
    by_machine: dict
    by_planned_reason: dict

    @classmethod
    def empty(cls) -> "GapAttribution":
        return cls(*(LossBucket() for _ in _BUCKET_NAMES), {}, {})

    def merge(self, other: "GapAttribution"):
        for name in _BUCKET_NAMES:
            getattr(self, name).merge(getattr(other, name))

        for target, source in (
            (self.by_machine, other.by_machine),
            (self.by_planned_reason, other.by_planned_reason),
        ):
            for key, bucket in source.items():
                target.setdefault(key, LossBucket()).merge(bucket)

    def to_api(self) -> dict:
        def ranked(buckets, key_name):
            items = sorted(buckets.items(), key=lambda item: item[1].tonnes, reverse=True)
            return [{key_name: key, **bucket.to_api()} for key, bucket in items]

        return {
            "calculation_status": "estimated",
            "method": ATTRIBUTION_METHOD,
            "measured_output_gap": self.measured_gap.to_api(include_minutes=False),
            "planned_downtime": self.planned_downtime.to_api(),
            "unplanned_downtime": self.unplanned_downtime.to_api(),
            "other_or_speed_loss": self.other_or_speed_loss.to_api(include_minutes=False),
            "unexplained_gap": self.unexplained_gap.to_api(include_minutes=False),
            "uncapped_downtime_potential": {
                "planned_downtime": self.planned_downtime_uncapped.to_api(),
                "unplanned_downtime": self.unplanned_downtime_uncapped.to_api(),
            },
            "by_machine": ranked(self.by_machine, "machine"),
            "by_planned_reason": ranked(self.by_planned_reason, "reason"),
        }


def attribute_run_gap(
    config: PackConfig,
    periods,
    planned_events,
    fault_events,
    window_start: datetime,
    window_end: datetime,
    run_start: datetime,
    run_end: datetime,
) -> GapAttribution:
    """
    periods:        [{"start", "end", "expected_packs", "actual_pallets", "loss_reason_recorded"}]
                    - the run's hourly periods that belong to the window.
    planned_events: [{"start", "end", "reason"}]
    fault_events:   [{"start", "end", "machine"}]
    `end` of an open event must already be set to `now` by the caller.
    """
    result = GapAttribution.empty()

    if not periods:
        return result

    lower = max(window_start, run_start)
    upper = min(window_end, run_end)

    coverage = merge_intervals(
        clip_interval((p["start"], p["end"]), lower, upper) for p in periods
    )

    planned_by_reason = {}
    for event in planned_events:
        pieces = intersect_intervals([(event["start"], event["end"])], coverage)
        planned_by_reason.setdefault(event["reason"], []).extend(pieces)

    planned_union = merge_intervals(i for pieces in planned_by_reason.values() for i in pieces)

    faults_by_machine = {}
    for event in fault_events:
        pieces = intersect_intervals([(event["start"], event["end"])], coverage)
        pieces = subtract_intervals(pieces, planned_union)
        faults_by_machine.setdefault(event["machine"], []).extend(pieces)

    unplanned_union = merge_intervals(i for pieces in faults_by_machine.values() for i in pieces)

    planned_minutes = total_minutes(planned_union)
    unplanned_minutes = total_minutes(unplanned_union)
    planned_potential = config.minutes_to_packs(planned_minutes)
    unplanned_potential = config.minutes_to_packs(unplanned_minutes)

    expected = sum((to_decimal(p["expected_packs"]) for p in periods), ZERO)
    actual = sum((config.pallets_to_packs(p["actual_pallets"]) for p in periods), ZERO)
    gap = max(expected - actual, ZERO)

    planned_attributed = min(planned_potential, gap)
    unplanned_attributed = min(unplanned_potential, gap - planned_attributed)
    remainder = gap - planned_attributed - unplanned_attributed

    explained_shortfall = sum(
        (
            max(to_decimal(p["expected_packs"]) - config.pallets_to_packs(p["actual_pallets"]), ZERO)
            for p in periods
            if p.get("loss_reason_recorded")
        ),
        ZERO,
    )
    other = min(remainder, explained_shortfall)
    unexplained = remainder - other

    result.measured_gap.add(config, gap)
    result.planned_downtime.add(config, planned_attributed, planned_minutes)
    result.unplanned_downtime.add(config, unplanned_attributed, unplanned_minutes)
    result.other_or_speed_loss.add(config, other)
    result.unexplained_gap.add(config, unexplained)
    result.planned_downtime_uncapped.add(config, planned_potential, planned_minutes)
    result.unplanned_downtime_uncapped.add(config, unplanned_potential, unplanned_minutes)

    # Share each capped total across machines / reasons by their own
    # merged minutes, so a breakdown always sums to the capped total
    # and a machine can never be credited more than the gap.
    _allocate(result.by_machine, faults_by_machine, unplanned_attributed, config)
    _allocate(result.by_planned_reason, planned_by_reason, planned_attributed, config)

    return result


def _allocate(target: dict, pieces_by_key: dict, attributed_packs: Decimal, config: PackConfig):
    minutes_by_key = {key: total_minutes(pieces) for key, pieces in pieces_by_key.items()}
    total = sum(minutes_by_key.values(), ZERO)

    for key, minutes in minutes_by_key.items():
        if minutes <= 0:
            continue
        share = attributed_packs * minutes / total
        target.setdefault(key, LossBucket()).add(config, share, minutes)


# ==========================================================
# ESTIMATED OEE
# ==========================================================

OEE_METHOD = (
    "Estimated OEE = Availability x Performance x Estimated Quality. "
    "Availability = run time / planned production time, where planned "
    "production time = reported hourly period minutes - planned downtime "
    "minutes, and run time = planned production time - unplanned "
    "downtime minutes. Performance = (actual packs / target packs per "
    "minute) / run time. Estimated Quality = palletised packs / X-ray "
    "pack count from end-of-shift/run X-ray captures; it covers only "
    "post-X-ray losses."
)


def estimate_oee(
    period_minutes,
    planned_minutes,
    unplanned_minutes,
    effective_output_minutes,
    quality_palletised_packs=None,
    quality_xray_packs=None,
    quality_unavailable_reason=None,
) -> dict:
    """effective_output_minutes = sum over runs of actual packs / that
    run's target speed, i.e. how many minutes of perfect running the
    real output represents (unit-consistent across products)."""
    period = to_decimal(period_minutes) or ZERO
    planned_production = period - (to_decimal(planned_minutes) or ZERO)
    run_time = planned_production - (to_decimal(unplanned_minutes) or ZERO)
    effective = to_decimal(effective_output_minutes) or ZERO

    result = {
        "availability_percent": None,
        "performance_percent": None,
        "estimated_quality_percent": None,
        "estimated_oee_percent": None,
        "calculation_status": "unavailable",
        "calculation_method": OEE_METHOD,
        "unavailable_reason": None,
    }

    if period <= 0 or planned_production <= 0:
        result["unavailable_reason"] = "No reported production time in this window."
        return result

    availability = max(run_time, ZERO) / planned_production
    result["availability_percent"] = as_number(availability * HUNDRED, PERCENT_PLACES)

    if run_time <= 0:
        result["calculation_status"] = "partial"
        result["unavailable_reason"] = (
            "No run time remained after downtime, so Performance cannot be calculated."
        )
        return result

    performance = effective / run_time
    result["performance_percent"] = as_number(performance * HUNDRED, PERCENT_PLACES)

    palletised = to_decimal(quality_palletised_packs)
    xray = to_decimal(quality_xray_packs)

    if palletised is None or xray is None or xray <= 0 or palletised > xray:
        result["calculation_status"] = "partial"
        result["unavailable_reason"] = quality_unavailable_reason or (
            "No usable X-ray count covers this output, so Quality - and "
            "therefore Estimated OEE - cannot be calculated. Quality is "
            "never assumed to be 100%."
        )
        return result

    quality = palletised / xray
    result["estimated_quality_percent"] = as_number(quality * HUNDRED, PERCENT_PLACES)
    result["estimated_oee_percent"] = as_number(
        availability * performance * quality * HUNDRED, PERCENT_PLACES
    )
    result["calculation_status"] = "estimated"
    return result


# ==========================================================
# WEEKLY TONNAGE TARGET
# ==========================================================


def weekly_target_progress(target_tonnes, actual_tonnes, week_window, now, has_data: bool) -> dict:
    """Green/red compares actual tonnes with the target pro-rated to
    how far through the production week `now` is (linear over the
    whole Monday 06:00 - Monday 06:00 week) - never the final
    percentage alone."""
    target = to_decimal(target_tonnes)
    actual = to_decimal(actual_tonnes) or ZERO
    fraction = elapsed_fraction(week_window, now)

    result = {
        "target_tonnes": as_number(target, TONNES_PLACES),
        "actual_tonnes": as_number(actual, TONNES_PLACES),
        "tonnes_remaining": None,
        "percent_complete": None,
        "expected_tonnes_by_now": None,
        "week_elapsed_percent": as_number(fraction * HUNDRED, PERCENT_PLACES),
        "target_status": "grey",
        "status_reason": None,
    }

    if target is None or target <= 0:
        result["status_reason"] = "No weekly target has been set."
        return result

    expected_by_now = target * fraction
    result["tonnes_remaining"] = as_number(max(target - actual, ZERO), TONNES_PLACES)
    result["percent_complete"] = as_number(actual / target * HUNDRED, PERCENT_PLACES)
    result["expected_tonnes_by_now"] = as_number(expected_by_now, TONNES_PLACES)

    if not has_data:
        result["status_reason"] = "No timestamped production data has been recorded this week yet."
        return result

    if actual >= expected_by_now:
        result["target_status"] = "green"
        result["status_reason"] = "On or ahead of the pace needed to reach the weekly target."
    else:
        result["target_status"] = "red"
        result["status_reason"] = "Behind the pace needed to reach the weekly target."

    return result


# ==========================================================
# ATTENTION AND FRESHNESS
# ==========================================================


def line_attention(achievement_percent, open_faults: int) -> tuple[str, str]:
    achievement = to_decimal(achievement_percent)

    if open_faults > 0:
        noun = "fault" if open_faults == 1 else "faults"
        return "red", f"{open_faults} open {noun} on this line."

    if achievement is None:
        return "grey", "Not enough production data in this window."

    shown = quantize(achievement, PERCENT_PLACES)

    if achievement < ACHIEVEMENT_AMBER_PERCENT:
        return "red", f"Production achievement {shown}% is below 85%."
    if achievement < ACHIEVEMENT_GREEN_PERCENT:
        return "amber", f"Production achievement {shown}% is between 85% and 95%."
    return "green", f"Production achievement {shown}% is 95% or above."


def freshness(
    has_active_run: bool,
    last_hourly_update_at: datetime | None,
    active_run_started_at: datetime | None,
    now: datetime,
    stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES,
) -> dict:
    if not has_active_run:
        return {
            "stale_status": "no_active_run",
            "stale_reason": "No active production run.",
            "minutes_since_last_hourly_update": None,
        }

    reference = last_hourly_update_at or active_run_started_at
    if reference is None:
        return {
            "stale_status": "unknown",
            "stale_reason": "No timestamp is available for this run.",
            "minutes_since_last_hourly_update": None,
        }

    minutes = minutes_between(reference, now)
    shown = as_number(minutes, MINUTES_PLACES)

    if minutes > stale_after_minutes:
        status = "stale"
        reason = (
            f"No hourly update for {shown} minutes."
            if last_hourly_update_at
            else f"No hourly update since the run started {shown} minutes ago."
        )
    else:
        status = "current"
        reason = None

    return {
        "stale_status": status,
        "stale_reason": reason,
        "minutes_since_last_hourly_update": shown if last_hourly_update_at else None,
    }
