import { ATTENTION } from './constants'
import { formatMinutes, formatPercent, formatTonnes } from './format'
import type { AttentionStatus, LineSummary } from './types'
import type { Tone } from './ui/MetricCard'
import { Panel } from './ui/Panel'
import { EmptyState } from './ui/states'
import { StatusBadge } from './ui/StatusBadge'

const ATTENTION_TONE: Record<AttentionStatus, Tone> = {
  red: 'bad',
  amber: 'warn',
  green: 'good',
  grey: 'neutral',
}

/** One card per line, the lines that need attention first. Status and
 * explanation are the backend's (docs "Line attention status"). */
export function LinePerformance({ lines }: { lines: LineSummary[] }) {
  const ordered = [...lines].sort(
    (a, b) => ATTENTION[a.attention_status].order - ATTENTION[b.attention_status].order,
  )

  return (
    <Panel title="Line performance">
      {ordered.length === 0 ? (
        <EmptyState>No line data was returned for this period.</EmptyState>
      ) : (
        <ul className="pd-lines">
          {ordered.map((line) => (
            <li key={line.production_line}>
              <article
                className={`pd-line pd-line--${line.attention_status}`}
                aria-labelledby={`line-${line.production_line}`}
              >
                <header className="pd-line__header">
                  <h3 id={`line-${line.production_line}`}>{line.production_line}</h3>
                  <StatusBadge tone={ATTENTION_TONE[line.attention_status]}>
                    {ATTENTION[line.attention_status].label}
                  </StatusBadge>
                </header>
                <p className="pd-line__explanation">{line.attention_explanation}</p>

                {line.output.hourly_update_count > 0 ? (
                  <dl className="pd-line__figures">
                    <div>
                      <dt>Of expected</dt>
                      <dd>{formatPercent(line.output.production_achievement_percent)}</dd>
                    </div>
                    <div>
                      <dt>Actual</dt>
                      <dd>{formatTonnes(line.output.actual_tonnes)}</dd>
                    </div>
                    <div>
                      <dt>Net shortfall</dt>
                      <dd>{formatTonnes(line.output.output_gap_tonnes)}</dd>
                    </div>
                    <div>
                      <dt>Planned stops</dt>
                      <dd>{formatMinutes(line.downtime_minutes.planned)}</dd>
                    </div>
                    <div>
                      <dt>Unplanned</dt>
                      <dd>{formatMinutes(line.downtime_minutes.unplanned)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className="pd-muted">{(line.reported_palletised_output?.hourly_update_count ?? 0) > 0
                    ? `Output reported: ${formatTonnes(line.reported_palletised_output!.actual_tonnes)} nominal. No comparable readings with a known standard.`
                    : 'No hourly updates in this period.'}</p>
                )}

                <p className="pd-line__meta">
                  {line.active_run
                    ? `Running: ${line.active_run.product} for ${line.active_run.customer} · ${line.active_run.line_technician}`
                    : 'No active run'}
                  {line.open_faults > 0 &&
                    ` · ${line.open_faults} open ${line.open_faults === 1 ? 'fault' : 'faults'}`}
                </p>
                {line.freshness.stale_status === 'stale' && (
                  <p className="pd-line__stale">{line.freshness.stale_reason ?? 'Hourly updates are overdue.'}</p>
                )}
              </article>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
