# ==========================================================
# TONNAGEFLOW PULSE
# Dashboard report builders
# ==========================================================
#
# Pure: turns rows from database.get_dashboard_window_data() (plus a
# TimeWindow and `now`) into the JSON contracts the protected
# management dashboard reads. No database, network or clock access -
# every figure comes from src/pulse_calculations.py.
#
# Window membership (documented, not hidden):
#   - Shift, factory-day and weekly windows select an hourly update by
#     its operational shift instance (the run's recorded shift), so a
#     period ending at a shift boundary stays with the shift that
#     produced it. Rolling 24h selects by period end. The whole period's
#     expected/actual output is counted.
#   - Downtime minutes are clipped to the run's reported hourly periods
#     and to `attribution_bounds` (the window, widened to cover the
#     included periods for shift-based windows) before being converted
#     to lost output. Fault counts only include faults overlapping the
#     window itself.
#   - Legacy hourly updates have a submission timestamp but no captured
#     period start/end, so they cannot be placed in any window; they are
#     counted in `legacy_hourly_updates_without_timestamp`.

from collections import defaultdict
from datetime import datetime

try:
    from . import pulse_calculations as calc
    from .factory_time import factory_date_of, production_week_start_date
except ImportError:
    import pulse_calculations as calc
    from factory_time import factory_date_of, production_week_start_date


LINE_LEVEL_OEE_NOTE = (
    "Production achievement and Estimated OEE are line-level only. "
    "Machine-level OEE would need per-machine output counts (packs "
    "passing each machine) and per-machine ideal rates; Pulse captures "
    "machine faults and downtime, but not per-machine output."
)


def _config_or_none(run):
    try:
        return calc.PackConfig.from_row(run)
    except (ValueError, TypeError, KeyError):
        return None


def _open_end(moment, now):
    return moment if moment is not None else now


def _fault_in_window(fault, window, now):
    return fault["opened_at"] < window.end and _open_end(fault["resolved_at"], now) > window.start


def _faults_in_window(data, window, now):
    return [fault for fault in data["faults"] if _fault_in_window(fault, window, now)]


class _LineAccumulator:
    def __init__(self, name):
        self.name = name
        self.output = calc.OutputTotals()
        self.attribution = calc.GapAttribution.empty()
        self.coverage_minutes = calc.ZERO
        self.effective_output_minutes = calc.ZERO
        self.open_faults = 0
        self.active_run = None
        self.xray_rows = []


def _periods_for(rows):
    return [
        {
            "start": row["period_started_at"],
            "end": row["period_ended_at"],
            "expected_packs": row["expected_packs"],
            "actual_pallets": row["actual_pallets"],
            "loss_reason_recorded": bool(
                row.get("other_loss_reason") or row.get("unexplained_loss_reason")
            ),
        }
        for row in rows
        if row["period_started_at"] is not None and row["period_ended_at"] is not None
    ]


def _accumulate(data, window, now):
    lines = {name: _LineAccumulator(name) for name in data["lines"]}
    runs = {run["id"]: run for run in data["runs"]}
    data_issues = []

    def line_for(name):
        if name not in lines:
            lines[name] = _LineAccumulator(name)
        return lines[name]

    hourly_by_run = defaultdict(list)
    for row in data["hourly"]:
        hourly_by_run[row["production_run_id"]].append(row)

    planned_by_run = defaultdict(list)
    for row in data["planned"]:
        planned_by_run[row["production_run_id"]].append(row)

    bounds_start, bounds_end = data.get("attribution_bounds", (window.start, window.end))

    faults_by_run = defaultdict(list)
    for row in data["faults"]:
        faults_by_run[row["production_run_id"]].append(row)
        if row["production_status"] == "Ongoing" and _fault_in_window(row, window, now):
            line_for(row["production_line"]).open_faults += 1

    for run in runs.values():
        accumulator = line_for(run["production_line"])
        if run["status"] == "Active":
            current = accumulator.active_run
            if current is None or run["started_at"] > current["started_at"]:
                accumulator.active_run = run

    for run_id, rows in hourly_by_run.items():
        run = runs.get(run_id)
        if run is None:
            continue

        config = _config_or_none(run)
        if config is None:
            data_issues.append(
                f"Run {run_id} has an invalid pack configuration and was excluded from calculations."
            )
            continue

        accumulator = line_for(run["production_line"])
        periods = _periods_for(rows)

        for period in periods:
            accumulator.output.add_period(config, period["expected_packs"], period["actual_pallets"])
            accumulator.effective_output_minutes += (
                config.pallets_to_packs(period["actual_pallets"]) / config.target_speed_ppm
            )

        run_end = _open_end(run["finished_at"], now)
        lower = max(bounds_start, run["started_at"])
        upper = min(bounds_end, run_end)
        accumulator.coverage_minutes += calc.total_minutes(
            calc.clip_interval((p["start"], p["end"]), lower, upper) for p in periods
        )

        accumulator.attribution.merge(
            calc.attribute_run_gap(
                config,
                periods,
                [
                    {"start": e["started_at"], "end": _open_end(e["ended_at"], now), "reason": e["reason"]}
                    for e in planned_by_run.get(run_id, [])
                ],
                [
                    {"start": f["opened_at"], "end": _open_end(f["resolved_at"], now), "machine": f["machine"]}
                    for f in faults_by_run.get(run_id, [])
                ],
                bounds_start,
                bounds_end,
                run["started_at"],
                run_end,
            )
        )

    for row in data["xray"]:
        line_for(row["production_line"]).xray_rows.append(row)

    return lines, data_issues


def _quality_inputs(xray_rows):
    if not xray_rows:
        return None, None, None

    unusable = [r for r in xray_rows if r["waste_status"] in ("unavailable", "data_quality_warning")]
    if unusable:
        return None, None, (
            "At least one X-ray capture in this window was unavailable or "
            "failed its data-quality check, so Estimated Quality is not calculated."
        )

    palletised = sum((calc.to_decimal(r["palletised_packs"]) for r in xray_rows), calc.ZERO)
    xray = sum((calc.to_decimal(r["xray_pack_count"]) for r in xray_rows), calc.ZERO)
    return palletised, xray, None


def _oee(accumulator):
    palletised, xray, reason = _quality_inputs(accumulator.xray_rows)
    return calc.estimate_oee(
        accumulator.coverage_minutes,
        accumulator.attribution.planned_downtime.minutes,
        accumulator.attribution.unplanned_downtime.minutes,
        accumulator.effective_output_minutes,
        quality_palletised_packs=palletised,
        quality_xray_packs=xray,
        quality_unavailable_reason=reason,
    )


def _active_run_api(active):
    if active is None:
        return None

    return {
        "run_id": active["id"],
        "line_technician": active["line_technician"],
        "shift": active["shift"],
        "customer": active["customer"],
        "product": active["product"],
        "format": active["format"],
        "started_at": active["started_at"],
        "pallets_remaining": calc.as_number(active["pallets_remaining"], calc.PALLETS_PLACES),
        "total_pallets_completed": calc.as_number(active["total_pallets_completed"], calc.PALLETS_PLACES),
    }


def _line_summary(accumulator, data, now, stale_after_minutes):
    status, explanation = calc.line_attention(
        accumulator.output.achievement_percent, accumulator.open_faults
    )
    active = accumulator.active_run
    last_hourly = data["last_hourly"].get(accumulator.name)

    return {
        "production_line": accumulator.name,
        "attention_status": status,
        "attention_explanation": explanation,
        "open_faults": accumulator.open_faults,
        "active_run": _active_run_api(active),
        "output": accumulator.output.to_api(),
        "downtime_minutes": {
            "planned": calc.as_number(accumulator.attribution.planned_downtime.minutes, calc.MINUTES_PLACES),
            "unplanned": calc.as_number(accumulator.attribution.unplanned_downtime.minutes, calc.MINUTES_PLACES),
        },
        "estimated_oee": _oee(accumulator),
        "freshness": {
            "latest_activity_at": data["latest_activity"].get(accumulator.name),
            "last_hourly_update_at": last_hourly,
            **calc.freshness(
                active is not None,
                last_hourly,
                active["started_at"] if active else None,
                now,
                stale_after_minutes,
            ),
        },
    }


def _site_accumulator(lines):
    site = _LineAccumulator("site")
    for accumulator in lines.values():
        site.output.merge(accumulator.output)
        site.attribution.merge(accumulator.attribution)
        site.coverage_minutes += accumulator.coverage_minutes
        site.effective_output_minutes += accumulator.effective_output_minutes
        site.open_faults += accumulator.open_faults
        site.xray_rows.extend(accumulator.xray_rows)
    return site


def _machine_ranking(lines):
    ranking = [
        (accumulator.name, machine, bucket)
        for accumulator in lines.values()
        for machine, bucket in accumulator.attribution.by_machine.items()
    ]
    ranking.sort(key=lambda item: item[2].tonnes, reverse=True)
    return [
        {"production_line": line, "machine": machine, **bucket.to_api()}
        for line, machine, bucket in ranking
    ]


def _site_attribution_api(lines, site):
    # Machine names are only unique within a line, so the site-level
    # machine ranking is rebuilt with the line attached.
    api = site.attribution.to_api()
    api["by_machine"] = _machine_ranking(lines)
    return api


def _site_freshness(line_summaries, data):
    statuses = [s["freshness"]["stale_status"] for s in line_summaries]

    if "stale" in statuses:
        status = "stale"
    elif "current" in statuses:
        status = "current"
    else:
        status = "no_active_run"

    return {
        "latest_activity_at": calc.latest(*data["latest_activity"].values()),
        "last_hourly_update_at": calc.latest(*data["last_hourly"].values()),
        "stale_status": status,
        "stale_lines": [
            s["production_line"] for s in line_summaries if s["freshness"]["stale_status"] == "stale"
        ],
    }


def legacy_data_quality(data):
    """Says plainly how many hourly updates are missing from a
    time-window total, and why.

    Legacy hourly updates DO have a submission timestamp - created_at
    has always existed and is NOT NULL on every historical row. What
    they lack is a captured period START and END, so there is no honest
    way to say which shift, factory day or week their output belongs
    to. They remain excluded from any report that requires a reliable
    production period, and period_started_at / period_ended_at are
    never derived from created_at: a submission time is not a period
    boundary.

    The consequence is that a window covering that period reports a
    total lower than the factory actually produced. Every report that
    carries a total therefore carries this block, so a low figure is
    never presented as though it were complete.
    """
    count = data.get("legacy_hourly_without_timestamp") or 0

    if count == 0:
        return {
            "legacy_records_excluded": False,
            "legacy_record_count": 0,
            "message": None,
        }

    plural = "update" if count == 1 else "updates"

    return {
        "legacy_records_excluded": True,
        "legacy_record_count": count,
        "message": (
            f"{count} older hourly {plural} could not be included. They have a submission "
            "timestamp, but they do not have a captured period start and period end, so "
            "they cannot be placed in a shift, day or week. They remain excluded from "
            "reporting that requires a reliable production period. Totals for any window "
            "covering that time are lower than what was actually produced. The original "
            "records are unchanged and no period times have been estimated."
        ),
    }


def build_overview(data, window, now: datetime, stale_after_minutes=calc.DEFAULT_STALE_AFTER_MINUTES):
    lines, data_issues = _accumulate(data, window, now)
    line_summaries = [
        _line_summary(accumulator, data, now, stale_after_minutes) for accumulator in lines.values()
    ]
    site = _site_accumulator(lines)

    return {
        "generated_at": now,
        "window": window.to_api(),
        "freshness": {**_site_freshness(line_summaries, data), "stale_after_minutes": stale_after_minutes},
        "output": site.output.to_api(),
        "gap_attribution": _site_attribution_api(lines, site),
        "estimated_oee": _oee(site),
        "open_faults": site.open_faults,
        "lines": line_summaries,
        "legacy_hourly_updates_without_timestamp": data["legacy_hourly_without_timestamp"],
        "data_quality": legacy_data_quality(data),
        "data_issues": data_issues,
        "notes": [LINE_LEVEL_OEE_NOTE],
    }


def build_gap_attribution(data, window, now: datetime):
    lines, data_issues = _accumulate(data, window, now)
    site = _site_accumulator(lines)

    return {
        "generated_at": now,
        "window": window.to_api(),
        "site": _site_attribution_api(lines, site),
        "lines": [
            {"production_line": accumulator.name, **accumulator.attribution.to_api()}
            for accumulator in lines.values()
        ],
        "data_quality": legacy_data_quality(data),
        "data_issues": data_issues,
    }


def _clipped_fault_minutes(fault, window, now):
    clipped = calc.clip_interval(
        (fault["opened_at"], _open_end(fault["resolved_at"], now)), window.start, window.end
    )
    return calc.ZERO if clipped is None else calc.minutes_between(*clipped)


def build_machine_summary(data, window, now: datetime):
    lines, _issues = _accumulate(data, window, now)
    attributed = {
        (entry["production_line"], entry["machine"]): entry for entry in _machine_ranking(lines)
    }

    machines = {}
    for fault in _faults_in_window(data, window, now):
        key = (fault["production_line"], fault["machine"])
        entry = machines.setdefault(
            key,
            {
                "production_line": key[0],
                "machine": key[1],
                "fault_count": 0,
                "open_faults": 0,
                "downtime_minutes_in_window": calc.ZERO,
                "maintenance_preventable": {"Yes": 0, "No": 0, "Unsure": 0, "not_recorded": 0},
            },
        )
        entry["fault_count"] += 1
        entry["open_faults"] += 1 if fault["production_status"] == "Ongoing" else 0
        entry["downtime_minutes_in_window"] += _clipped_fault_minutes(fault, window, now)
        entry["maintenance_preventable"][fault["maintenance_preventable"] or "not_recorded"] += 1

    items = []
    for key, entry in machines.items():
        loss = attributed.get(key, {})
        items.append(
            {
                **entry,
                "downtime_minutes_in_window": calc.as_number(
                    entry["downtime_minutes_in_window"], calc.MINUTES_PLACES
                ),
                "estimated_lost_tonnes": loss.get("estimated_lost_tonnes", 0.0),
                "estimated_lost_pallets": loss.get("estimated_lost_pallets", 0.0),
                "estimated_lost_packs": loss.get("estimated_lost_packs", 0.0),
                "machine_oee": None,
                "machine_oee_unavailable_reason": LINE_LEVEL_OEE_NOTE,
            }
        )

    items.sort(
        key=lambda item: (item["estimated_lost_tonnes"], item["downtime_minutes_in_window"]),
        reverse=True,
    )

    return {
        "generated_at": now,
        "window": window.to_api(),
        "ranking_basis": "estimated_lost_tonnes (capped attribution), then downtime minutes",
        "method": calc.ATTRIBUTION_METHOD,
        "machines": items,
        "data_quality": legacy_data_quality(data),
    }


ENGINEERING_CLASS_LABELS = {
    "Machine Setting": "machine_setup_or_setting",
    "Mechanical": "physical_component_failure",
}


def build_engineering_classification(data, window, now: datetime):
    def bucket():
        return {"fault_count": 0, "downtime_minutes_in_window": calc.ZERO}

    repair = defaultdict(bucket)
    preventable = defaultdict(bucket)
    status = defaultdict(bucket)

    for fault in _faults_in_window(data, window, now):
        minutes = _clipped_fault_minutes(fault, window, now)
        repair_key = ENGINEERING_CLASS_LABELS.get(fault["repair_classification"], "not_classified")
        preventable_key = (fault["maintenance_preventable"] or "not_recorded").lower()
        status_key = "open" if fault["production_status"] == "Ongoing" else "closed"

        for target, key in ((repair, repair_key), (preventable, preventable_key), (status, status_key)):
            target[key]["fault_count"] += 1
            target[key]["downtime_minutes_in_window"] += minutes

    def to_api(groups, keys):
        return {
            key: {
                "fault_count": groups[key]["fault_count"],
                "downtime_minutes_in_window": calc.as_number(
                    groups[key]["downtime_minutes_in_window"], calc.MINUTES_PLACES
                ),
            }
            for key in keys
        }

    return {
        "generated_at": now,
        "window": window.to_api(),
        "by_repair_classification": to_api(
            repair, ("machine_setup_or_setting", "physical_component_failure", "not_classified")
        ),
        "by_maintenance_preventable": to_api(preventable, ("yes", "no", "unsure", "not_recorded")),
        "by_status": to_api(status, ("open", "closed")),
        "data_quality": legacy_data_quality(data),
        "notes": [
            "Repair classification comes from the engineer's latest classified repair "
            "update; maintenance preventability is recorded only at fault closure and "
            "is never inferred from notes. 'not_classified' / 'not_recorded' include "
            "open faults and historical faults closed before these fields existed.",
        ],
    }


def build_xray_waste(data, window, now: datetime):
    items = []
    xray_total = calc.ZERO
    palletised_total = calc.ZERO
    usable = 0

    for row in data["xray"]:
        items.append(
            {
                "xray_capture_id": row["id"],
                "production_run_id": row["production_run_id"],
                "production_line": row["production_line"],
                "capture_point": row["capture_point"],
                "shift": row["shift"],
                "captured_at": row["captured_at"],
                "count_available": row["count_available"],
                "xray_pack_count": row["xray_pack_count"],
                "unavailable_reason": row["unavailable_reason"],
                "palletised_packs": calc.as_number(row["palletised_packs"], calc.PACKS_PLACES),
                "post_xray_pack_difference": calc.as_number(
                    row["post_xray_pack_difference"], calc.PACKS_PLACES
                ),
                "estimated_post_xray_waste_percent": calc.as_number(
                    row["estimated_waste_percent"], calc.PERCENT_PLACES
                ),
                "waste_status": row["waste_status"],
            }
        )
        if row["waste_status"] == "estimated":
            usable += 1
            xray_total += calc.to_decimal(row["xray_pack_count"])
            palletised_total += calc.to_decimal(row["palletised_packs"])

    waste = calc.xray_waste(xray_total, palletised_total) if usable else None

    return {
        "generated_at": now,
        "window": window.to_api(),
        "method": calc.XRAY_METHOD,
        "captures": items,
        "combined_estimate": {
            "captures_included": usable,
            "captures_excluded": len(items) - usable,
            "estimated_post_xray_waste_percent": (
                None if waste is None
                else calc.as_number(waste["estimated_post_xray_waste_percent"], calc.PERCENT_PLACES)
            ),
            "calculation_status": "estimated" if waste else "unavailable",
            "unavailable_reason": None if waste else "No usable X-ray count in this window.",
        },
        "data_quality": legacy_data_quality(data),
    }


def build_weekly_targets(target_rows, data, week_window, now: datetime):
    lines, _issues = _accumulate(data, week_window, now)
    site = _site_accumulator(lines)

    targets = {(row["scope"], row["production_line"]): row["target_tonnes"] for row in target_rows}

    def progress(scope, line, totals):
        return {
            "scope": scope,
            "production_line": line,
            **calc.weekly_target_progress(
                targets.get((scope, line)),
                totals.actual_tonnes,
                week_window,
                now,
                has_data=totals.hourly_update_count > 0,
            ),
        }

    return {
        "generated_at": now,
        "week": week_window.to_api(),
        "latest_activity_at": calc.latest(*data["latest_activity"].values()),
        "pace_method": (
            "Expected tonnes by now = weekly target x fraction of the "
            "Monday 06:00 - Monday 06:00 (Europe/London) week elapsed. "
            "Green when actual tonnes >= expected tonnes by now; red when "
            "behind; grey when no target is set or no timestamped "
            "production data exists yet this week."
        ),
        "site": progress("site", None, site.output),
        "lines": [progress("line", a.name, a.output) for a in lines.values()],
        "data_quality": legacy_data_quality(data),
    }


# ----------------------------------------------------------
# Changeovers (QC)
# ----------------------------------------------------------

DURATION_BANDS = (
    (15, "under_15_minutes"),
    (30, "15_to_30_minutes"),
    (60, "30_to_60_minutes"),
)


def _duration_band(minutes):
    if minutes is None:
        return "open"
    for limit, label in DURATION_BANDS:
        if minutes < limit:
            return label
    return "60_minutes_or_more"


def _weight_key(row):
    weight = row["new_pack_weight_kg"]
    if weight is None:
        weight = row["previous_pack_weight_kg"]
    return calc.as_number(weight, calc.TONNES_PLACES)


CHANGEOVER_GROUP_KEYS = {
    "line": lambda row: row["production_line"],
    "technician": lambda row: row["line_technician"],
    "shift": lambda row: row["shift"],
    "customer": lambda row: row["new_customer"] or row["previous_customer"],
    "product": lambda row: row["new_product"] or row["previous_product"],
    "pack_weight": _weight_key,
    "format": lambda row: row["new_format"] or row["previous_format"],
    "day": lambda row: factory_date_of(row["started_at"]).isoformat(),
    "week": lambda row: production_week_start_date(row["started_at"]).isoformat(),
    "month": lambda row: factory_date_of(row["started_at"]).strftime("%Y-%m"),
    "duration": lambda row: _duration_band(calc.to_decimal(row["duration_minutes"])),
}


def serialize_changeover(row):
    data = dict(row)
    data["changeover_id"] = data.pop("id")
    data["duration_minutes"] = calc.as_number(row["duration_minutes"], calc.MINUTES_PLACES)
    data["previous_pack_weight_kg"] = calc.as_number(row["previous_pack_weight_kg"], calc.TONNES_PLACES)
    data["new_pack_weight_kg"] = calc.as_number(row["new_pack_weight_kg"], calc.TONNES_PLACES)
    return data


def build_changeover_report(rows, group_by, now: datetime):
    groups = None

    if group_by is not None:
        key_of = CHANGEOVER_GROUP_KEYS[group_by]
        grouped = defaultdict(list)
        for row in rows:
            grouped[key_of(row)].append(row)

        groups = []
        for key, members in grouped.items():
            durations = [
                calc.to_decimal(m["duration_minutes"]) for m in members if m["duration_minutes"] is not None
            ]
            total = sum(durations, calc.ZERO)
            groups.append(
                {
                    "key": key,
                    "changeover_count": len(members),
                    "completed_count": len(durations),
                    "open_count": len(members) - len(durations),
                    "total_duration_minutes": calc.as_number(total, calc.MINUTES_PLACES),
                    "average_duration_minutes": (
                        calc.as_number(total / len(durations), calc.MINUTES_PLACES) if durations else None
                    ),
                    "longest_duration_minutes": (
                        calc.as_number(max(durations), calc.MINUTES_PLACES) if durations else None
                    ),
                }
            )
        groups.sort(key=lambda g: g["total_duration_minutes"], reverse=True)

    return {
        "generated_at": now,
        "definition": (
            "A changeover starts when the line technician selects Start "
            "Changeover and ends when the first acceptable packs of the new "
            "run are produced - not when the machines restart."
        ),
        "group_by": group_by,
        "groups": groups,
        "changeovers": [serialize_changeover(row) for row in rows],
    }
