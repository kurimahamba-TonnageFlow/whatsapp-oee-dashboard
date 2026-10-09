"""Operational evidence only. Financial placeholders never enter this data model."""
from collections import defaultdict
from datetime import timedelta
from . import live_dashboard as live, dashboard_reports as reports, pulse_calculations as calc
from .factory_time import resolve_window, FACTORY_TZ


def load_data(now):
    current, week = live.load_snapshot(now)
    previous_date = week.start.astimezone(FACTORY_TZ).date() - timedelta(days=7)
    previous, _ = live.load_snapshot(now, previous_date)
    # Reuse the established bulk readers. Previous-week history is needed only
    # for a like-for-like production comparison, not inferred from this week.
    data = dict(current)
    for key in ('runs', 'readings', 'planned', 'faults', 'stoppages', 'operating_changes'):
        data[key] = list({r['id']: r for r in previous[key] + current[key]}.values())
    data['runs'].sort(key=lambda r: r['started_at'])
    runs = {r['id']: r for r in data['runs']}
    for stop in data['stoppages']:
        reference = runs.get(stop.get('previous_production_run_id'), {})
        for field in ('pack_weight_kg', 'packs_per_case', 'cases_per_pallet'):
            stop['reference_' + field] = reference.get(field)
    # Reuse Management's existing per-line target reader.
    from .database import list_weekly_targets
    data['line_targets'] = list_weekly_targets(week.start.astimezone(FACTORY_TZ).date())
    return data, week


def select_lines(data, line):
    names = [line] if line else data['lines']
    runs = [r for r in data['runs'] if r['production_line'] in names]
    ids = {r['id'] for r in runs}
    return {**data, 'lines': names, 'runs': runs,
            'readings': [r for r in data['readings'] if r['production_run_id'] in ids],
            'planned': [r for r in data['planned'] if r['production_run_id'] in ids],
            'faults': [r for r in data['faults'] if r['production_line'] in names],
            'stoppages': [r for r in data['stoppages'] if r['production_line'] in names]}


def selected_readings(data, window, now):
    unique = {(r['production_run_id'], r.get('hour_start') or r['id']): r
              for r in sorted(data['readings'], key=lambda r: r['id'])}
    result = []
    for row in unique.values():
        end = row.get('period_ended_at')
        start = row.get('period_started_at')
        if not start or not end or end > now or end <= start:
            continue
        member = row.get('shift_window_start')
        included = (window.start < end <= window.end if window.kind == 'rolling_24h'
                    else member is not None and window.start <= member < window.end)
        if included:
            result.append(row)
    return result


def report_data(data, window, now):
    rows = selected_readings(data, window, now)
    return {**data, 'hourly': [{**r, 'actual_pallets': r['pallets_completed'],
                              'expected_packs': r.get('expected_packs')} for r in rows],
            'line_stops': data['stoppages'], 'xray': [],
            'legacy_hourly_without_timestamp': sum(r.get('period_ended_at') is None for r in data['readings']),
            'latest_activity': {}, 'last_hourly': {},
            'attribution_bounds': (min([window.start] + [r['period_started_at'] for r in rows]),
                                   max([window.end] + [r['period_ended_at'] for r in rows]))}


def weekly_values(data, week, now, line):
    # Management's new configurable site target is deliberately not allocated
    # arbitrarily to a selected line. No line target => "Not set".
    targets = data['targets'] if not line else [t for t in data.get('line_targets', []) if t['scope'] == 'line' and t['production_line'] == line]
    result = live.weekly_production({**data, 'targets': targets}, week, now)
    if line:
        result['site'] = line
    elapsed = max(0, min((now - week.start).total_seconds(), (week.end - week.start).total_seconds()))
    result['elapsed_percent'] = elapsed / (week.end - week.start).total_seconds() * 100
    result['elapsed_days'] = elapsed / 86400
    result['comparison_percent'] = None
    result['comparison_note'] = 'Comparable previous-week coverage unavailable'
    previous = live.reporting_week(week.start.astimezone(FACTORY_TZ).date() - timedelta(days=7))
    cutoff = min(previous.end, previous.start + timedelta(seconds=elapsed))
    prior = live.weekly_production({**data, 'targets': []}, previous, cutoff)
    def coverage(window, end):
        runs = {r['id']: r for r in data['runs']}
        covered = defaultdict(list)
        for row in selected_readings(data, window, end):
            covered[runs[row['production_run_id']]['production_line']].append((row['period_started_at'], row['period_ended_at']))
        return {name: calc.total_minutes(calc.merge_intervals(spans)) for name, spans in covered.items()}
    current_coverage = coverage(week, now)
    if (result['actual_tonnes'] is not None and prior['actual_tonnes'] and current_coverage
            and current_coverage == coverage(previous, cutoff)
            and not result['excluded_readings'] and not prior['excluded_readings']):
        result['comparison_percent'] = (result['actual_tonnes'] / prior['actual_tonnes'] - 1) * 100
        result['comparison_note'] = 'Against the same elapsed previous week; matching reported line coverage'
    return result


def downtime_and_drivers(data, window, now):
    """Clip to scheduled line time; allocate overlapping stops once, oldest first."""
    end = min(window.end, now)
    drivers = defaultdict(lambda: {'minutes': calc.ZERO, 'events': set(), 'fault_ids': set()})
    totals = {'planned_minutes': 0.0, 'unplanned_minutes': 0.0, 'not_scheduled_minutes': 0.0}
    for line in data['lines']:
        runs = [r for r in data['runs'] if r['production_line'] == line]
        ids = {r['id'] for r in runs}
        stops = [s for s in data['stoppages'] if s['production_line'] == line]
        unscheduled = calc.intersect_intervals(
            [(s['started_at'], s['ended_at'] or end) for s in stops if s['kind'] == 'not_scheduled'], [(window.start, end)])
        totals['not_scheduled_minutes'] += float(calc.total_minutes(unscheduled))
        coverage = calc.subtract_intervals(calc.intersect_intervals(
            [(r['started_at'], r['finished_at'] or end) for r in runs] +
            [(s['started_at'], s['ended_at'] or end) for s in stops if s['kind'] != 'not_scheduled'],
            [(window.start, end)]), unscheduled)
        planned = [(p['started_at'], p['ended_at'] or end, 'Planned stop', p['reason'], ('planned', p['id']))
                   for p in data['planned'] if p['production_run_id'] in ids]
        unplanned = [(f['opened_at'], f['resolved_at'] or end, f['machine'], f['reason'], ('fault', f['id']))
                     for f in data['faults'] if f['production_line'] == line]
        for stop in stops:
            if stop['kind'] == 'not_scheduled': continue
            is_planned = stop['kind'] in ('changeover', 'handover')
            reason = stop['kind'].replace('_', ' ').title()
            if stop.get('reason'): reason += ': ' + stop['reason']
            (planned if is_planned else unplanned).append((stop['started_at'], stop['ended_at'] or end,
                'Planned stop' if is_planned else 'Line stop', reason, ('stop', stop['id'])))
        allocated = []
        for category, events in [('planned_minutes', planned), ('unplanned_minutes', unplanned)]:
            for a, b, machine, reason, identity in sorted(events, key=lambda v: (v[0], str(v[4]))):
                spans = calc.subtract_intervals(calc.intersect_intervals([(a, b)], coverage), allocated)
                if not spans: continue
                allocated += spans
                minutes = calc.total_minutes(spans)
                totals[category] += float(minutes)
                row = drivers[(line, machine, reason)]
                row['minutes'] += minutes
                row['events'].add(identity)
                if identity[0] == 'fault': row['fault_ids'].add(identity[1])
    total = totals['planned_minutes'] + totals['unplanned_minutes']
    totals['unplanned_percent'] = totals['unplanned_minutes'] / total * 100 if total else None
    rows = [dict(line=line, machine=machine, cause=cause, minutes=float(v['minutes']),
                 events=len(v['events']), fault_ids=sorted(v['fault_ids']), estimated_tonnes=None,
                 investigation=('Review the recorded stop sequence and waiting time.' if machine == 'Planned stop'
                                else 'Review fault history and confirm the cause with Engineering.'))
            for (line, machine, cause), v in drivers.items() if v['minutes'] > 0]
    rows.sort(key=lambda r: (-r['minutes'], r['line'], r['cause']))
    # Existing estimates group by machine, not individual cause. Do not allocate
    # that quantity to causes without supporting observations.
    return totals, rows[:3]


def build_intelligence(data, week, now, period='production_week', line=None):
    configured_lines = data['lines']
    data = select_lines(data, line)
    window = week if period == 'production_week' else resolve_window(period, now)
    overview = reports.build_overview(report_data(data, window, now), window, now)
    weekly = weekly_values(data, week, now, line)
    summary = live.build_snapshot(data, week, now)
    downtime, drivers = downtime_and_drivers(data, window, now)
    output = overview['output']
    gap = output['output_gap_tonnes'] if output['hourly_update_count'] else None
    # No evidence currently separates delayed/recoverable/confirmed quantities.
    loss = dict(total_tonnes=gap, unclassified_tonnes=gap, recoverable_tonnes=None,
                delayed_tonnes=None, confirmed_unrecovered_tonnes=None,
                note='Recoverability not yet assessed. Output gap is not confirmed commercial loss.')
    rows = []
    for state in summary['lines']:
        issue = next((f for f in sorted(data['faults'], key=lambda f: f['opened_at'])
                      if f['production_line'] == state['name'] and f['production_status'] == 'Ongoing' and f['resolved_at'] is None), None)
        current_issue = issue['reason'] if issue else ('Changeover in progress' if state['status'] == 'changeover' else 'Not scheduled' if state['status'] == 'not_scheduled' else 'No unresolved production fault')
        rows.append({**{k: v for k, v in state.items() if k != 'trend'}, 'current_issue': current_issue,
                     'current_fault_id': issue['id'] if issue else None})
    return dict(generated_at=now, window=window.to_api(), configured_lines=configured_lines,
                selected_line=line, weekly=weekly, lines=rows, output_gap=loss,
                downtime=downtime, loss_drivers=drivers,
                ranking_method='Ranked by non-overlapping recorded stop minutes. Per-cause tonnes are not reliably attributable.',
                line_stops=overview['line_stops'], data_issues=overview['data_issues'],
                material_flow=[{'stage':name, 'connected':name == 'Packaging',
                                'tonnes':weekly['actual_tonnes'] if name == 'Packaging' else None}
                               for name in ['Intake','Process','Packaging','Finished Goods','Dispatch']])
