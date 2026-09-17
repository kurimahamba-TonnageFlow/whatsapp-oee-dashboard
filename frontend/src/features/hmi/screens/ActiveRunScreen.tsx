import { useEffect, useState } from 'react'
import { ProgressBar } from '../components/ProgressBar'
import { StatusPill } from '../components/StatusPill'
import { deriveRunProgress, formatDuration, statusToneForProgress } from '../progress'
import type { ActiveRunRecord } from '../types'

interface ActiveRunScreenProps {
  run: ActiveRunRecord
  onHourlyUpdate: () => void
  onPlannedDowntime: () => void
  onReportToEngineer: () => void
  onCompleteRun: () => void
  onExitRestart: () => void
}

export function ActiveRunScreen({
  run,
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

  const progress = deriveRunProgress(run, now)
  const tone = statusToneForProgress(progress.percentComplete, progress.outputGapPacks)
  const startedAt = new Date(run.startedAtIso)

  return (
    <div className="hmi-screen hmi-active-run">
      <header className="hmi-active-run__header">
        <div>
          <h1>{run.form.productionLine}</h1>
          <p>
            {run.form.customer} — {run.form.product} ({run.form.packType})
          </p>
        </div>
        <StatusPill tone={tone}>
          {tone === 'green' ? 'On target' : tone === 'amber' ? 'At risk' : 'Behind'}
        </StatusPill>
      </header>

      <ProgressBar
        percentComplete={progress.percentComplete}
        tone={tone}
        label="Run completion"
      />

      <dl className="hmi-review-list hmi-active-run__facts">
        <div className="hmi-review-list__row">
          <dt>Technician</dt>
          <dd>{run.form.lineTechnician}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Shift</dt>
          <dd>{run.form.shift}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Target speed</dt>
          <dd>{run.form.targetSpeedPpm} packs/min</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Start time</dt>
          <dd>{startedAt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Run duration</dt>
          <dd>{formatDuration(progress.elapsedMinutes)}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets completed</dt>
          <dd>{progress.totalPalletsCompleted}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets remaining</dt>
          <dd>{progress.palletsRemaining}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Expected output</dt>
          <dd>{Math.round(progress.expectedPacks)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Actual output</dt>
          <dd>{Math.round(progress.actualPacks)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Output gap</dt>
          <dd>{Math.round(progress.outputGapPacks)} packs</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Planned downtime</dt>
          <dd>{run.plannedDowntimeMinutes} min</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Unplanned downtime</dt>
          <dd>{run.unplannedDowntimeMinutes} min</dd>
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
        <button type="button" className="hmi-ghost-button" onClick={onExitRestart}>
          Exit or Restart Run
        </button>
      </div>
    </div>
  )
}
