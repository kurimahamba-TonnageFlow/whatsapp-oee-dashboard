"""Run-associated production evidence, not a measure of technician competence.
Selected completed runs are included in full, by their start date. Between-run
stops have no run technician attribution and are deliberately excluded.
"""
from collections import defaultdict
try:
    from . import pulse_calculations as calc
except ImportError:
    import pulse_calculations as calc


def build_technician_performance(runs, readings, planned, faults):
    readings_by_run, planned_by_run, faults_by_line = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in readings:
        readings_by_run[row['production_run_id']].append(row)
    for row in planned:
        planned_by_run[row['production_run_id']].append(row)
    for row in faults:
        faults_by_line[row['production_line']].append(row)
    grouped = defaultdict(list)
    for run in runs:
        grouped[run["line_technician"]].append(run)
    result = []
    for technician, selected in grouped.items():
        expected_pallets = actual_pallets = expected_tonnes = actual_tonnes = calc.ZERO
        gap_pallets = gap_tonnes = reported_tonnes = calc.ZERO
        scheduled = covered = planned_minutes = unplanned_minutes = calc.ZERO
        comparable_runs = 0
        limitations = set()
        for run in selected:
            start, end = run["started_at"], run["finished_at"]
            cfg = calc.PackConfig.from_row(run)
            if end is None or end <= start:
                limitations.add("Run timing is missing or invalid.")
                continue
            span = [(start,end)]
            scheduled += calc.total_minutes(span)
            p = calc.intersect_intervals([(r["started_at"],r["ended_at"] or end)
                for r in planned_by_run[run["id"]]],span)
            u = calc.subtract_intervals(calc.intersect_intervals([(r["opened_at"],r["resolved_at"] or end)
                for r in faults_by_line[run["production_line"]]],span),p)
            planned_minutes += calc.total_minutes(p)
            unplanned_minutes += calc.total_minutes(u)
            intervals = []
            comparable = False
            for reading in readings_by_run[run["id"]]:
                pallets = calc.to_decimal(reading.get("pallets_completed"))
                if pallets is None:
                    limitations.add("Production reading missing.")
                    continue
                reported_tonnes += cfg.packs_to_tonnes(cfg.pallets_to_packs(pallets))
                a,b = reading["period_started_at"],reading["period_ended_at"]
                if a is None or b is None or a < start or b > end or b <= a:
                    limitations.add("Reading timing missing or outside its run; excluded from comparisons.")
                    continue
                if calc.intersect_intervals(intervals,[(a,b)]):
                    limitations.add("Overlapping reporting periods need review; excluded from ranking.")
                    continue
                review = calc.reconcile_production(run.get("standard_speed_ppm"),a,b,
                    cfg.pallets_to_packs(pallets),p,u)
                if not review["comparable"]:
                    limitations.update(review["limitations"])
                    continue
                intervals.append((a,b))
                comparable = True
                expected_pallets += cfg.packs_to_pallets(review["target_packs"])
                actual_pallets += pallets
                expected_tonnes += cfg.packs_to_tonnes(review["target_packs"])
                actual_tonnes += cfg.packs_to_tonnes(review["actual_packs"])
                gap_pallets += cfg.packs_to_pallets(review["shortfall_packs"])
                gap_tonnes += cfg.packs_to_tonnes(review["shortfall_packs"])
            covered += calc.total_minutes(intervals)
            comparable_runs += int(comparable)
        complete = scheduled > 0 and covered == scheduled and not limitations
        if covered < scheduled:
            limitations.add("Missing readings or unknown standards: comparison coverage is incomplete.")
        number=lambda x: calc.as_number(x,calc.TONNES_PLACES)
        result.append(dict(line_technician=technician,completed_runs=len(selected),comparable_runs=comparable_runs,
            expected_pallets=number(expected_pallets),actual_pallets=number(actual_pallets),
            expected_tonnes=number(expected_tonnes),actual_tonnes=number(actual_tonnes),
            reported_tonnes=number(reported_tonnes),output_gap_pallets=number(gap_pallets),output_gap_tonnes=number(gap_tonnes),
            target_achievement_percent=calc.as_number(actual_tonnes/expected_tonnes*100,calc.PERCENT_PLACES)
                if complete and expected_tonnes > 0 else None,
            planned_downtime_minutes=calc.as_number(planned_minutes,calc.MINUTES_PLACES),
            unplanned_downtime_minutes=calc.as_number(unplanned_minutes,calc.MINUTES_PLACES),
            data_completion_rate_percent=calc.as_number(covered/scheduled*100,calc.PERCENT_PLACES) if scheduled else None,
            coverage_complete=complete,limitations=sorted(limitations),
            lines=sorted({r["production_line"] for r in selected}),
            shifts=sorted({r["shift"] for r in selected}),products=sorted({r["product"] for r in selected}),
            customers=sorted({r["customer"] for r in selected}),run_ids=[r["id"] for r in selected]))
    return result
