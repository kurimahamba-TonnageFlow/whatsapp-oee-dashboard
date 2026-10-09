"""Shared card/dashboard trial calculations; no stored production data is rewritten."""
import os
from decimal import Decimal, InvalidOperation
try:
    from . import pulse_calculations as c
except ImportError:
    import pulse_calculations as c


def trial_quality():
    try:
        value = Decimal(os.getenv("PULSE_TRIAL_QUALITY_PERCENT", "98"))
        return value if value.is_finite() and 0 <= value <= 100 else None
    except InvalidOperation:
        return None


def excluded_reasons():
    return {s.strip().casefold() for s in os.getenv("PULSE_OEE_EXCLUDED_PLANNED_REASONS", "").split(",") if s.strip()}


def period_report(speed, start, end, actual, planned=None, faults=None, note=None,
                  gross_packs=None, rejected_packs=None):
    """None stops means unavailable; an empty, successfully loaded list means no recorded stops.
    Palletised output is explicitly provisional unless period-matched gross/reject counts exist.
    Planned intervals take precedence over faults, so overlapping stops count once.
    """
    duration = c.minutes_between(start, end)
    rate, packs = c.to_decimal(speed), c.to_decimal(actual)
    rate = rate if rate is not None and rate.is_finite() else None
    packs = packs if packs is not None and packs.is_finite() else None
    target = rate * duration if rate is not None and rate > 0 and duration > 0 else None
    variance = packs - target if target is not None and packs is not None else None
    coverage = [(start, end)]
    known = planned is not None and faults is not None
    p = c.intersect_intervals([(r["started_at"], r.get("ended_at") or end) for r in planned or []], coverage)
    u = c.subtract_intervals(c.intersect_intervals([(r["opened_at"], r.get("resolved_at") or end) for r in faults or []], coverage), p)
    excluded = c.intersect_intervals([(r["started_at"], r.get("ended_at") or end) for r in planned or []
                                     if r.get("reason", "").casefold() in excluded_reasons()], coverage)
    pm, um, em = c.total_minutes(p), c.total_minutes(u), c.total_minutes(excluded)
    gross, rejects = c.to_decimal(gross_packs), c.to_decimal(rejected_packs)
    measured = gross is not None and rejects is not None and gross.is_finite() and rejects.is_finite() and gross >= 0 and 0 <= rejects <= gross
    gross_valid = gross is None and rejects is None or measured
    basis = gross if measured else packs
    q = (100 * (gross-rejects)/gross if measured and gross > 0 else None if measured else trial_quality())
    valid = known and rate is not None and rate > 0 and duration > 0 and packs is not None and packs >= 0 and gross_valid
    unavailable = ('Awaiting downtime data' if not known else 'Invalid time, speed or output data') if not valid else None
    reasons = list(dict.fromkeys(str(r.get("reason") or '').strip() for r in (planned or []) + (faults or [])))
    if note: reasons.append(note.strip())
    unexplained = max(target-packs-rate*(pm+um), c.ZERO) if valid and target is not None else None
    # When output already exceeds the standard, loss attribution is not reliable.
    if variance is not None and variance > 0: unexplained = None
    return {"target_packs": target, "actual_packs": packs, "pack_variance": variance,
            "shortfall_packs": max(-variance,c.ZERO) if variance is not None else None,
            "attainment_percent": c.percent(packs,target) if target is not None and packs is not None else None,
            "period_minutes": duration, "standard_speed_ppm": rate,
            "planned_minutes": pm if known else None, "unplanned_minutes": um if known else None,
            "excluded_minutes": em if known else None, "unexplained_shortfall": unexplained,
            "reasons": [r for r in reasons if r],
            "_oee": {"valid": valid, "reason": unavailable, "duration": duration,
                     "excluded": em, "unplanned": um, "ideal_minutes": basis/rate if valid else c.ZERO,
                     "gross": basis if valid else c.ZERO, "quality": q, "measured": measured}}


def aggregate_oee(reports):
    inputs = [r["_oee"] for r in reports]
    reason = next((r["reason"] for r in inputs if not r["valid"]), None)
    result = dict(availability_percent=None, performance_percent=None, estimated_quality_percent=None,
                  estimated_oee_percent=None, calculation_status="unavailable", unavailable_reason=reason,
                  quality_basis="provisional", output_basis="Palletised packs - provisional output basis",
                  calculation_method="Availability x Performance x Quality. Only configured planned-stop exclusions reduce planned production time.", warnings=[])
    if not inputs or reason:
        result["unavailable_reason"] = reason or "No reported production time"
        return result
    measured = all(r["measured"] for r in inputs)
    if any(r["quality"] is None for r in inputs):
        result["unavailable_reason"] = "Quality assumption is missing or invalid"
        return result
    gross = sum((r["gross"] for r in inputs), c.ZERO)
    quality = (sum((r["gross"]*r["quality"] for r in inputs), c.ZERO)/gross if gross else inputs[0]["quality"])
    values = c.estimate_oee(sum((r["duration"] for r in inputs), c.ZERO),
                           sum((r["excluded"] for r in inputs), c.ZERO),
                           sum((r["unplanned"] for r in inputs), c.ZERO),
                           sum((r["ideal_minutes"] for r in inputs), c.ZERO),
                           provisional_quality_percent=quality)
    result.update(values)
    result["calculation_method"] = "Availability x Performance x Quality. Planned time excludes only configured stop reasons."
    result["quality_basis"] = "measured" if measured else "provisional"
    result["output_basis"] = "Gross packs including recorded rejects" if measured else "Palletised packs - provisional output basis"
    result["estimated_quality_percent"] = c.as_number(quality,c.PERCENT_PLACES)
    if values["performance_percent"] is not None and values["performance_percent"] > 100:
        result["warnings"].append("Performance above 100% - review speed, counts, conversion and downtime")
    return result


def report_api(report):
    return {k: c.as_number(v, c.PERCENT_PLACES if k.endswith("percent") else Decimal("0.000001"))
            if isinstance(v, Decimal) else v for k,v in report.items() if not k.startswith("_")}
