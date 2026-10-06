# ==========================================================
# TONNAGEFLOW PULSE
# Fixed-hour Production report
# ==========================================================
#
# Pure: turns rows from database.get_hourly_report_data() for one shift
# (plus the shift window and `now`) into each line's clock hours - the
# LINE result and every PRODUCT RUN result in each hour. No database,
# network or clock access; every figure comes from
# src/pulse_calculations.py (run_hour_result / line_hour_result, whose
# two denominators are documented there).
#
#   - Hours are consecutive 60-minute UTC slots from the shift start, so
#     night shifts cross midnight and the clock changes are exact.
#   - An hour with no reading is "no_reading" (null), never 0%.
#   - Faults are matched to the LINE, not the run that reported them: a
#     fault left open persists across shifts and changeovers, and its
#     time is counted once.
#   - Changeover / Other stoppages lower the line hour only.

from collections import defaultdict
from datetime import datetime

try:
    from . import pulse_calculations as calc
    from .factory_time import CLOCK_HOUR, clock_hour_label, clock_hours_between
except ImportError:
    import pulse_calculations as calc
    from factory_time import CLOCK_HOUR, clock_hour_label, clock_hours_between


def _open_end(moment, now):
    return moment if moment is not None else now


def _packs(value):
    return calc.as_number(value, calc.PACKS_PLACES)


def _minutes(value):
    return calc.as_number(value, calc.MINUTES_PLACES)


def _percent(value):
    return calc.as_number(value, calc.PERCENT_PLACES)


def _reasons_api(reasons):
    return [{"kind": r["kind"], "reason": r["reason"], "minutes": _minutes(r["minutes"])} for r in reasons]


def _stops_api(result):
    return {
        "stopped_minutes": _minutes(result["stopped_minutes"]),
        "planned_minutes": _minutes(result["planned_minutes"]),
        "unplanned_minutes": _minutes(result["unplanned_minutes"]),
        "stop_reasons": _reasons_api(result["reasons"]),
    }


def _run_result_api(run, result):
    percent = result["output_vs_target_percent"]
    return {
        "reconciliation": calc.reconciliation_api(result["reconciliation"]),
        "run_id": run["id"],
        "product": run["product"],
        "customer": run["customer"],
        "line_technician": run["line_technician"],
        "status": result["status"],
        "applicable_start": result["applicable_start"],
        "applicable_end": result["applicable_end"],
        "applicable_minutes": _minutes(result["applicable_minutes"]),
        "is_partial_hour": result["is_partial_hour"],
        "target_speeds": [
            {"from": s["from"], "to": s["to"], "speed_ppm": _packs(s["speed_ppm"])}
            for s in result["target_speeds"]
        ],
        "actual_speed_ppm": _packs(result["actual_speed_ppm"]),
        "target_packs": _packs(result["target_packs"]),
        "actual_packs": _packs(result["actual_packs"]),
        "output_vs_target_percent": _percent(percent),
        "is_low_output": calc.is_low_output(percent),
        **_stops_api(result),
    }


def _line_result_api(result):
    percent = result["output_vs_target_percent"]
    stops = _stops_api(result)
    not_scheduled = result.get("not_scheduled_minutes", calc.ZERO)
    if not_scheduled > 0:
        # Shown beside the reasons, but never in the stopped minutes.
        stops["stop_reasons"] = stops["stop_reasons"] + [
            {"kind": "not_scheduled", "reason": calc.NOT_SCHEDULED_REASON, "minutes": _minutes(not_scheduled)}
        ]
    return {
        "status": result["status"],
        "target_packs": _packs(result["target_packs"]),
        "actual_packs": _packs(result["actual_packs"]),
        "output_vs_target_percent": _percent(percent),
        "is_low_output": calc.is_low_output(percent),
        "covered_minutes": _minutes(result["covered_minutes"]),
        "unaccounted_minutes": _minutes(result["unaccounted_minutes"]),
        "not_scheduled_minutes": _minutes(not_scheduled),
        "stoppage_reference_missing": result["stoppage_reference_missing"],
        **stops,
    }


RESTART_DELAY_REASON = "Restart delay"


def _stoppage_events(stoppages, now):
    """Line stops between product runs. Each is ONE interval on the line
    (counted once); its reasons are split for reporting only:
      - Changeover: physical work (start -> End Changeover) and new-run
        setup (End Changeover -> new run starts). Planned.
      - Handover: End Shift -> the incoming technician's Start Run, with
        both technicians named. Planned.
      - Other: unplanned, with the written reason (cause -> Resolve).
      - Restart delay: unplanned, Resolve -> the next run starts. Its own
        reason, so the fix and the wait to restart are never merged.
      - Not scheduled: the line was not scheduled to produce. Accounted
        for, but in no target and in neither planned nor unplanned."""
    planned, unplanned, for_line = [], [], []
    for stop in stoppages:
        end = _open_end(stop["ended_at"], now)
        kind = stop["kind"]
        if kind == "changeover":
            label = "Changeover"
            physical_end = stop.get("physical_ended_at")
            if physical_end is not None:
                planned.append((stop["started_at"], physical_end, "Changeover — physical work"))
                planned.append((physical_end, end, "Changeover — new-run setup"))
            else:
                planned.append((stop["started_at"], end, "Changeover — physical work"))
        elif kind == "handover":
            incoming = stop.get("ended_by") or "incoming technician"
            label = f"Handover ({stop.get('started_by') or 'outgoing'} → {incoming})"
            planned.append((stop["started_at"], end, label))
        elif kind == "restart_delay":
            label = RESTART_DELAY_REASON
            unplanned.append((stop["started_at"], end, label))
        elif kind == calc.NOT_SCHEDULED:
            label = calc.NOT_SCHEDULED_REASON
        else:
            label = f"Other: {stop['reason']}" if stop.get("reason") else "Other"
            unplanned.append((stop["started_at"], end, label))
        for_line.append(
            {
                "start": stop["started_at"],
                "end": end,
                "kind": kind,
                "reason": label,
                "reference_speed_ppm": stop.get("reference_speed_ppm"),
            }
        )
    return planned, unplanned, for_line


def build_hourly_report(data, window, now: datetime, production_line=None):
    runs_by_line = defaultdict(list)
    for run in data["runs"]:
        runs_by_line[run["production_line"]].append(run)

    readings = {(r["production_run_id"], r["hour_start"]): r["pallets_completed"] for r in data["readings"]}

    notes = {(r["production_run_id"],r["hour_start"]): r.get("other_loss_reason") for r in data["readings"]}

    changes_by_run = defaultdict(list)
    for change in data["speed_changes"]:
        changes_by_run[change["production_run_id"]].append(change)

    operating_by_run = defaultdict(list)
    for change in data.get("operating_changes", []):
        operating_by_run[change["production_run_id"]].append(change)

    planned_by_run = defaultdict(list)
    for event in data["planned"]:
        planned_by_run[event["production_run_id"]].append(
            (event["started_at"], _open_end(event["ended_at"], now), event["reason"])
        )

    faults_by_line = defaultdict(list)
    for fault in data["faults"]:
        faults_by_line[fault["production_line"]].append(
            (fault["opened_at"], _open_end(fault["resolved_at"], now), f"{fault['machine']} — {fault['reason']}")
        )

    stoppages_by_line = defaultdict(list)
    for stop in data["stoppages"]:
        stoppages_by_line[stop["production_line"]].append(stop)

    # The current hour is shown (in progress); later hours are not.
    hours = clock_hours_between(window.start, min(window.end, now)) if now > window.start else []

    lines = [production_line] if production_line else data["lines"]
    report_lines = []
    for line in lines:
        runs = runs_by_line.get(line, [])
        faults = faults_by_line.get(line, [])
        stop_planned, stop_unplanned, stop_events = _stoppage_events(stoppages_by_line.get(line, []), now)
        run_planned = [event for run in runs for event in planned_by_run.get(run["id"], [])]

        slots = []
        reconciliation_results = []
        for hour_start in hours:
            run_parts = []
            for run in runs:
                result = calc.run_hour_result(
                    hour_start,
                    now,
                    run["started_at"],
                    run["finished_at"],
                    [(None, calc.to_decimal(run.get("standard_speed_ppm") or run["target_speed_ppm"]))],
                    calc.to_decimal(run["packs_per_case"]) * calc.to_decimal(run["cases_per_pallet"]),
                    readings.get((run["id"], hour_start)),
                    planned_by_run.get(run["id"], []),
                    faults,
                    standard=run.get("standard_speed_ppm"),
                    operating=operating_by_run.get(run["id"], []),
                )
                if result is not None:
                    run_parts.append((run, result))
                    result["reconciliation"]["reported_explanation"] = notes.get((run["id"],hour_start))
                    if result["status"] != "in_progress":
                        reconciliation_results.append(result["reconciliation"])

            stop_results = []
            run_cover = [(r["applicable_start"],r["applicable_end"]) for _,r in run_parts]
            for stop in stop_events:
                if stop["kind"] == calc.NOT_SCHEDULED:
                    continue
                pieces = calc.subtract_intervals(calc.intersect_intervals(
                    [(stop["start"],stop["end"])],[(hour_start,min(hour_start+CLOCK_HOUR,now))]),run_cover)
                for a,b in pieces:
                    planned_stop = stop["kind"] in ("changeover","handover")
                    stop_results.append(calc.reconcile_production(stop.get("reference_speed_ppm"),a,b,calc.ZERO,
                        [(a,b)] if planned_stop else [], [] if planned_stop else [(a,b)]))
            reconciliation_results.extend(stop_results)
            line_result = calc.line_hour_result(
                hour_start,
                now,
                [result for _run, result in run_parts],
                stop_events,
                run_planned + stop_planned,
                faults + stop_unplanned,
            )
            slots.append(
                {
                    "hour_start": hour_start,
                    "hour_end": hour_start + CLOCK_HOUR,
                    "hour_label": clock_hour_label(hour_start),
                    "is_complete": hour_start + CLOCK_HOUR <= now,
                    "line": {**_line_result_api(line_result), "reconciliation": calc.reconciliation_api(calc.summarise_reconciliations(
                        [r["reconciliation"] for _,r in run_parts]+stop_results))},
                    "runs": [_run_result_api(run, result) for run, result in run_parts],
                }
            )

        # A result needs target time: idle and wholly Not scheduled hours
        # are never "the latest completed hour".
        completed = [
            slot for slot in slots
            if slot["is_complete"] and slot["line"]["status"] not in ("idle", "not_scheduled")
        ]
        report_lines.append(
            {
                "production_line": line,
                "reconciliation": calc.reconciliation_api(calc.summarise_reconciliations(reconciliation_results)),
                "latest_completed_hour": completed[-1] if completed else None,
                "hours": slots,
            }
        )

    return {
        "generated_at": now,
        "window": window.to_api(),
        "measure": calc.OUTPUT_VS_TARGET_LABEL,
        "method": calc.OUTPUT_VS_TARGET_METHOD,
        "low_output_percent": calc.as_number(calc.LOW_OUTPUT_PERCENT, calc.PERCENT_PLACES),
        "denominators": {
            "run": (
                "The run's own target packs for the minutes of the hour it was open, "
                "at the fixed agreed standard. Unknown legacy standards are not invented."
            ),
            "line": (
                "The sum of the runs' target packs plus Handover, Changeover, Other and "
                "Restart delay minutes at the outgoing run's agreed standard. Not scheduled "
                "minutes are in no target and in neither planned nor unplanned downtime. "
                "Minutes covered by no run and no recorded stop are shown as unaccounted "
                "and are not in the denominator."
            ),
        },
        "lines": report_lines,
    }
