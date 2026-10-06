import { useState } from 'react'
import { useProtectedData } from '../management/session/useProtectedData'
import * as dashboardApi from './api'
import { MISSING } from './format'
import type { HourLineResult, HourRunResult, HourSlot, HourlyLine, StopReason } from './types'
import { Panel } from './ui/Panel'
import { EmptyState, ErrorState, LoadingState, RefreshFailed } from './ui/states'

const SHIFT_OPTIONS = [
  { value: 0, label: 'This shift' },
  { value: 1, label: 'Previous shift' },
  { value: 2, label: 'Two shifts ago' },
]

function number(value: number | null, digits = 0): string {
  if (value === null || !Number.isFinite(value)) return MISSING
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}

function minutes(value: number): string {
  return `${Math.round(value)} min`
}

/** The measure itself: a percentage, or plain words when there is none.
 * Never 0% for an hour nobody reported. Below 60% is orange. */
function Measure({ result }: { result: HourLineResult | HourRunResult }) {
  if (result.status === 'no_reading') return <span className="pd-hour__none">No reading</span>
  if (result.status === 'in_progress') return <span className="pd-muted">In progress</span>
  if (result.status === 'idle') return <span className="pd-muted">Not running</span>
  if (result.status === 'not_scheduled') return <span className="pd-muted">Not scheduled</span>
  if (result.output_vs_target_percent === null) return <span className="pd-muted">{MISSING}</span>
  return (
    <span className={result.is_low_output ? 'pd-hour__pct pd-hour__pct--low' : 'pd-hour__pct'}>
      {number(result.output_vs_target_percent, 1)}%
    </span>
  )
}

const KIND_LABEL: Record<StopReason['kind'], string> = {
  planned: 'Planned',
  unplanned: 'Unplanned',
  not_scheduled: 'Not scheduled',
}

function Reasons({ reasons }: { reasons: StopReason[] }) {
  if (reasons.length === 0) return null
  return (
    <ul className="pd-hour__reasons">
      {reasons.map((reason) => (
        <li key={`${reason.kind}-${reason.reason}`}>
          <span className={`pd-hour__kind pd-hour__kind--${reason.kind}`}>
            {KIND_LABEL[reason.kind]}
          </span>{' '}
          {reason.reason} · {minutes(reason.minutes)}
        </li>
      ))}
    </ul>
  )
}

function speeds(run: HourRunResult): string {
  const distinct = [...new Set(run.target_speeds.map((segment) => segment.speed_ppm))]
  return distinct.map((speed) => number(speed, 0)).join(' → ')
}

function LatestHour({ line }: { line: HourlyLine }) {
  const slot = line.latest_completed_hour
  if (!slot) {
    return <p className="pd-muted">No completed hour on this line in this shift.</p>
  }
  const runs = slot.runs
  return (
    <div className="pd-hour__latest" aria-label={`${line.production_line} latest completed hour`}>
      <div>
        <p className="pd-hour__latest-label">Latest completed hour · {slot.hour_label}</p>
        <p className="pd-hour__latest-value">
          <Measure result={slot.line} />
        </p>
        <p className="pd-muted">
          {runs.length === 0
            ? 'No product run in this hour'
            : runs.map((run) => `${run.product} · ${run.line_technician}`).join(' / ')}
        </p>
      </div>
      <dl className="pd-hour__facts">
        <div>
          <dt>Target</dt>
          <dd>{number(slot.line.target_packs)} packs</dd>
        </div>
        <div>
          <dt>Actual</dt>
          <dd>{slot.line.actual_packs === null ? MISSING : `${number(slot.line.actual_packs)} packs`}</dd>
        </div>
        <div>
          <dt>Stopped</dt>
          <dd>{minutes(slot.line.stopped_minutes)}</dd>
        </div>
      </dl>
    </div>
  )
}

function HourRows({ slot }: { slot: HourSlot }) {
  const runs = slot.runs
  // A separate LINE row when the line hour differs from its one run:
  // several runs, no run (a whole-hour stop), a changeover/other stop or
  // an unaccounted gap.
  const showLineRow =
    runs.length !== 1 ||
    slot.line.unaccounted_minutes > 0 ||
    (slot.line.not_scheduled_minutes ?? 0) > 0 ||
    slot.line.stopped_minutes !== runs[0].stopped_minutes
  return (
    <>
      {runs.map((run, index) => (
        <tr key={`${slot.hour_start}-${run.run_id}`} className={index === 0 ? 'pd-hour__first' : undefined}>
          {index === 0 && (
            <th scope="rowgroup" rowSpan={runs.length + (showLineRow ? 1 : 0)} className="pd-hour__label">
              {slot.hour_label}
            </th>
          )}
          <td>
            {run.product}
            {run.is_partial_hour && <small className="pd-muted"> · {minutes(run.applicable_minutes)}</small>}
          </td>
          <td>{run.line_technician}</td>
          <td className="pd-num">{speeds(run)}</td>
          <td className="pd-num">{number(run.actual_speed_ppm, 1)}</td>
          <td className="pd-num">
            <Measure result={run} />
          </td>
          <td className="pd-num">{minutes(run.stopped_minutes)}</td>
          <td>
            <Reasons reasons={run.stop_reasons} />
          </td>
        </tr>
      ))}
      {showLineRow && (
        <tr className={`pd-hour__line-row${runs.length === 0 ? ' pd-hour__first' : ''}`}>
          {runs.length === 0 && (
            <th scope="rowgroup" className="pd-hour__label">
              {slot.hour_label}
            </th>
          )}
          <td colSpan={4}>
            <strong>Line</strong>
            {slot.line.status === 'stopped' && ' · no product run (line stopped between runs)'}
            {slot.line.status === 'not_scheduled' && ' · not scheduled to produce (no target, not downtime)'}
            {slot.line.unaccounted_minutes > 0 && ` · ${minutes(slot.line.unaccounted_minutes)} unaccounted`}
          </td>
          <td className="pd-num">
            <Measure result={slot.line} />
          </td>
          <td className="pd-num">{minutes(slot.line.stopped_minutes)}</td>
          <td>
            <Reasons reasons={slot.line.stop_reasons} />
          </td>
        </tr>
      )}
    </>
  )
}

function LineHours({ line }: { line: HourlyLine }) {
  const hours = [...line.hours].reverse() // newest first
  const anything = hours.some((slot) => slot.line.status !== 'idle')
  return (
    <div className="pd-hour" role="group" aria-labelledby={`hourly-${line.production_line}`}>
      <h3 id={`hourly-${line.production_line}`} className="pd-hour__title">
        {line.production_line}
      </h3>
      <LatestHour line={line} />
      {anything ? (
        <div className="pd-table-wrap" tabIndex={0} role="region" aria-label={`${line.production_line} hours table`}>
          <table className="pd-table pd-hour__table" aria-label={`${line.production_line} hours`}>
            <thead>
              <tr>
                <th scope="col">Hour</th>
                <th scope="col">Product</th>
                <th scope="col">Technician</th>
                <th scope="col" className="pd-num">Target speed</th>
                <th scope="col" className="pd-num">Actual speed</th>
                <th scope="col" className="pd-num">Output vs target (all stops)</th>
                <th scope="col" className="pd-num">Stopped</th>
                <th scope="col">Stops and reasons</th>
              </tr>
            </thead>
            <tbody>
              {hours
                .filter((slot) => slot.line.status !== 'idle')
                .map((slot) => (
                  <HourRows key={slot.hour_start} slot={slot} />
                ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState>Nothing has run on this line in this shift.</EmptyState>
      )}
    </div>
  )
}

/** Each line's clock hours for one shift. Every figure is the backend's
 * (src/hourly_reports.py); this component only lays them out. */
export function HourlyOutput({ line, refreshToken = 0 }: { line: string; refreshToken?: number }) {
  const [shiftOffset, setShiftOffset] = useState(0)
  const report = useProtectedData(
    (token, signal) =>
      dashboardApi.getHourly(token, { shift_offset: shiftOffset, production_line: line || null }, signal),
    JSON.stringify({ shiftOffset, line, refreshToken }),
  )

  return (
    <Panel
      title="Output vs target (all stops) — by hour"
      actions={
        <label className="pd-inline-field">
          <span>Hourly view shift</span>
          <select value={shiftOffset} onChange={(event) => setShiftOffset(Number(event.target.value))}>
            {SHIFT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      }
    >
      {report.error && report.data && <RefreshFailed message={report.error} />}
      {report.data ? (
        <>
          <p className="pd-table-caption">
            {report.data.window.label} · product, technician, target and actual speed for each clock hour.
            Below {report.data.low_output_percent}% is shown in orange. Quality is not measured, so this is
            not OEE.
          </p>
          <div className="pd-hour__lines">
            {report.data.lines.map((hourlyLine) => (
              <LineHours key={hourlyLine.production_line} line={hourlyLine} />
            ))}
          </div>
          <details className="pd-footnote">
            <summary>How this is calculated</summary>
            <p>{report.data.method}</p>
            <p>Product run: {report.data.denominators.run}</p>
            <p>Line: {report.data.denominators.line}</p>
          </details>
        </>
      ) : report.error ? (
        <ErrorState message={report.error} onRetry={report.reload} />
      ) : (
        <LoadingState>Loading hourly output…</LoadingState>
      )}
    </Panel>
  )
}
