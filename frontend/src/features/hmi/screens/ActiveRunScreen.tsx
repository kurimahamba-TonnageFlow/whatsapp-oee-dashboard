import { useEffect, useState } from 'react'
import { ProgressBar } from '../components/ProgressBar'
import { StatusPill } from '../components/StatusPill'
import { formatDuration, statusToneForAchievement } from '../progress'
import type { PendingAction } from '../idempotency'
import type { RunState } from '../types'

interface ActiveRunScreenProps {
  state: RunState
  isRefreshing: boolean
  refreshError: string | null
  pendingAction: PendingAction | null
  onRefresh: () => void
  onResolvePending: () => void
  onDiscardPending: () => void
  onHourlyUpdate: () => void
  onPlannedDowntime: () => void
  onReportToEngineer: () => void
  onCompleteRun: () => void
  onExitRestart: () => void
}

function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

/**
 * The backend is the authority: `serverMinutes` was measured from the
 * server clock at `generatedAt`. Between refreshes the tablet only adds
 * the time that has visibly passed since that response arrived, so the
 * figure keeps ticking without ever becoming the stored value - and
 * every refresh replaces it with the server's own figure again.
 */
function liveMinutes(serverMinutes: number | null, generatedAt: string, now: Date) {
  if (serverMinutes === null) return null

  const sinceResponse = (now.getTime() - new Date(generatedAt).getTime()) / 60_000
  // A tablet clock running behind the server would otherwise subtract time.
  return Math.round(serverMinutes + Math.max(sinceResponse, 0))
}

export function ActiveRunScreen({
  state,
  isRefreshing,
  refreshError,
  pendingAction,
  onRefresh,
  onResolvePending,
  onDiscardPending,
  onHourlyUpdate,
  onPlannedDowntime,
  onReportToEngineer,
  onCompleteRun,
  onExitRestart,
}: ActiveRunScreenProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(interval)
  }, [])

  const { run, progress } = state
  const tone = statusToneForAchievement(progress.production_achievement_percent)

  // An event in progress must never read as 0 just because it has not
  // been closed. These tick between refreshes and are corrected by the
  // server's own figure on every refresh.
  const activePlannedMinutes = liveMinutes(
    progress.planned_downtime_active_minutes,
    state.generated_at,
    now,
  )
  const activeChangeoverMinutes = liveMinutes(
    progress.changeover_active_minutes,
    state.generated_at,
    now,
  )
  const minutesSinceRefresh = Math.max(
    (now.getTime() - new Date(state.generated_at).getTime()) / 60_000,
    0,
  )
  const plannedTotal = run.starting_pallets_remaining
  const percentComplete = plannedTotal > 0 ? (run.total_pallets_completed / plannedTotal) * 100 : 0
  const elapsedMinutes = Math.max((now.getTime() - new Date(run.started_at).getTime()) / 60000, 0)
  const hourlyUpdateDue = now >= new Date(progress.next_hourly_update_due_at)

  return (
    <div className="hmi-screen hmi-active-run">
      <header className="hmi-active-run__header">
        <div>
          <h1>{run.production_line}</h1>
          <p>
            {run.customer} — {run.product} ({run.pack_type})
          </p>
        </div>
        <StatusPill tone={tone}>
          {tone === 'green'
            ? 'On target'
            : tone === 'amber'
              ? 'At risk'
              : tone === 'red'
                ? 'Behind'
                : 'No data yet'}
        </StatusPill>
      </header>

      {pendingAction && (
        <div className="hmi-inline-warning" role="alert">
          <p>
            {pendingAction.label} was not confirmed. Check and retry — Pulse will not record it
            twice.
          </p>
          <div className="hmi-form-actions">
            <button type="button" className="hmi-primary-button" onClick={onResolvePending}>
              Check and retry
            </button>
            <button type="button" className="hmi-secondary-button" onClick={onDiscardPending}>
              Discard
            </button>
          </div>
        </div>
      )}

      {state.open_planned_downtime && (
        <p className="hmi-inline-warning" role="status">
          Planned downtime in progress: {state.open_planned_downtime.reason} — running for{' '}
          <strong>{activePlannedMinutes} min</strong> (started{' '}
          {clockTime(state.open_planned_downtime.started_at)})
        </p>
      )}

      {state.open_changeover && (
        <p className="hmi-inline-warning" role="status">
          Changeover in progress to {state.open_changeover.new_customer} —{' '}
          {state.open_changeover.new_product} — running for{' '}
          <strong>{activeChangeoverMinutes} min</strong>
        </p>
      )}

      {hourlyUpdateDue && !state.open_planned_downtime && (
        <p className="hmi-inline-warning" role="status">
          Hourly update due
        </p>
      )}

      {refreshError && (
        <p className="hmi-inline-error" role="alert">
          {refreshError}
        </p>
      )}

      <ProgressBar percentComplete={percentComplete} tone={tone} label="Run completion" />

      <dl className="hmi-review-list hmi-active-run__facts">
        <div className="hmi-review-list__row">
          <dt>Technician</dt>
          <dd>{run.line_technician}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Shift</dt>
          <dd>{run.shift}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Target speed</dt>
          <dd>{run.target_speed_ppm} packs/min</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Start time</dt>
          <dd>{clockTime(run.started_at)}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Run duration</dt>
          <dd>{formatDuration(elapsedMinutes)}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets completed</dt>
          <dd>{run.total_pallets_completed}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets remaining</dt>
          <dd>{run.pallets_remaining}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Expected output</dt>
          <dd>{Math.round(progress.expected_packs)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Actual output</dt>
          <dd>{Math.round(progress.actual_packs)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Output gap</dt>
          <dd>{Math.round(progress.output_gap_packs)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Planned downtime (completed)</dt>
          <dd>{progress.planned_downtime_completed_minutes} min</dd>
        </div>
        {activePlannedMinutes !== null && (
          <div className="hmi-review-list__row hmi-review-list__row--active">
            <dt>Planned downtime (active now)</dt>
            <dd>{activePlannedMinutes} min</dd>
          </div>
        )}
        {activeChangeoverMinutes !== null && (
          <div className="hmi-review-list__row hmi-review-list__row--active">
            <dt>Changeover (active now)</dt>
            <dd>{activeChangeoverMinutes} min</dd>
          </div>
        )}
        <div className="hmi-review-list__row">
          <dt>Planned downtime to date</dt>
          <dd>
            {activePlannedMinutes === null
              ? progress.planned_downtime_minutes
              : Math.round(progress.planned_downtime_minutes + minutesSinceRefresh)}{' '}
            min
          </dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Unplanned downtime</dt>
          <dd>{progress.unplanned_downtime_minutes} min</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Open faults</dt>
          <dd>{progress.open_faults}</dd>
        </div>
      </dl>

      <div className="hmi-active-run__actions">
        <button type="button" className="hmi-primary-button" onClick={onHourlyUpdate}>
          Hourly Update
        </button>
        <button type="button" className="hmi-secondary-button" onClick={onPlannedDowntime}>
          Planned Downtime
        </button>
        <button type="button" className="hmi-danger-button" onClick={onReportToEngineer}>
          Report to Engineer
        </button>
        <button type="button" className="hmi-secondary-button" onClick={onCompleteRun}>
          Complete Run
        </button>
        <button
          type="button"
          className="hmi-ghost-button"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          {isRefreshing ? 'Refreshing…' : 'Refresh'}
        </button>
        <button type="button" className="hmi-ghost-button" onClick={onExitRestart}>
          Exit or Restart Run
        </button>
      </div>
    </div>
  )
}
