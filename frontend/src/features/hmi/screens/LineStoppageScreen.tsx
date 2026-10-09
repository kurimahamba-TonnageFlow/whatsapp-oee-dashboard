import { getCasepackerStatus, type CasepackerRequest } from '../../engineering/casepackerApi'
import { useEffect, useState } from 'react'
import { LINE_TECHNICIANS } from '../constants'
import { formatDuration } from '../progress'
import type { LineStoppageKind } from '../types'

export interface ActiveLineStoppage {
  linetech?: boolean
  stoppageId: number
  productionLine: string
  kind: LineStoppageKind
  reason: string | null
  startedAt: string
  startedBy: string | null
  /** Changeover only: End Changeover confirmed, new-run setup running. */
  physicalEndedAt?: string | null
  /** Set once the stop has fully ended (Other: Resolve). */
  endedAt: string | null
  durationMinutes: number | null
}

interface LineStoppageScreenProps {
  stoppage: ActiveLineStoppage
  isSubmitting: boolean
  errorMessage: string | null
  onEnd: (endedBy: string) => void
  onStartNewRun: () => void
  onHome: () => void
}

function minutesBetween(from: string, to: Date): number {
  return (to.getTime() - new Date(from).getTime()) / 60000
}

/** The Handover, Changeover or Other timer between runs. It belongs to
 * the line, not to either product run or technician. */
export function LineStoppageScreen({
  stoppage,
  isSubmitting,
  errorMessage,
  onEnd,
  onStartNewRun,
  onHome,
}: LineStoppageScreenProps) {
  const [now, setNow] = useState(() => new Date())
  const [endedBy, setEndedBy] = useState(stoppage.startedBy ?? '')
  const isChangeover = stoppage.kind === 'changeover'
  const [casepacker, setCasepacker] = useState<CasepackerRequest | null>(null)
  const [casepackerLoaded, setCasepackerLoaded] = useState(false)
  const [casepackerError, setCasepackerError] = useState(false)
  useEffect(() => {
    if (!isChangeover) return
    const controller = new AbortController()
    const load = async () => {
      try {
        const result = await getCasepackerStatus(stoppage.stoppageId, controller.signal)
        if (!controller.signal.aborted) {
          setCasepacker(result.request)
          setCasepackerLoaded(true)
          setCasepackerError(false)
        }
      } catch {
        if (!controller.signal.aborted) setCasepackerError(true)
      }
    }
    setCasepackerLoaded(false)
    void load()
    const timer = window.setInterval(() => { void load() }, 5000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [isChangeover, stoppage.stoppageId])
  const casepackerBlocked = isChangeover && (!casepackerLoaded || casepackerError || !!(casepacker && !casepacker.ready_at))
  const casepackerNotice = isChangeover && (
    <div role="status" className="hmi-timer-notice">
      {casepackerError ? 'Could not check casepacker readiness. Reconnecting... Starting is blocked until checked.'
        : !casepackerLoaded ? 'Checking casepacker readiness...'
        : casepacker ? <>
          <strong>{casepacker.ready_at ? 'Casepacker ready' : 'Waiting for Engineering - next run blocked'}</strong>
          <p>{casepacker.details}</p>
          <p>{casepacker.ready_at ? `Marked ready by ${casepacker.engineer}.` : casepacker.engineer ? `Accepted by ${casepacker.engineer}.` : 'Request sent. Waiting for an engineer to accept.'}</p>
        </> : 'No casepacker format change requested.'}
    </div>
  )

  const isHandover = stoppage.kind === 'handover'
  const isRestartDelay = stoppage.kind === 'restart_delay'
  const isNotScheduled = stoppage.kind === 'not_scheduled'
  const inSetup = isChangeover && !!stoppage.physicalEndedAt

  useEffect(() => {
    if (stoppage.endedAt) return
    const interval = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(interval)
  }, [stoppage.endedAt])

  if (stoppage.endedAt) {
    return (
      <div className="hmi-screen hmi-line-stoppage" role="status">
        <p className="hmi-run-started__mark">
          ✓ Stop resolved
          {stoppage.durationMinutes !== null && ` after ${formatDuration(stoppage.durationMinutes)}`}
        </p>
        <p>The line is ready. Start a new run when production resumes.</p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onHome}>
            Home
          </button>
          <button type="button" className="hmi-primary-button" onClick={onStartNewRun}>
            Start New Run
          </button>
        </div>
      </div>
    )
  }

  const elapsed = minutesBetween(stoppage.startedAt, now)

  if (isNotScheduled) {
    return (
      <div className="hmi-screen hmi-line-stoppage">
        <h1>Not scheduled — {stoppage.productionLine}</h1>
        <p className="hmi-planned-downtime__elapsed">Elapsed: {formatDuration(elapsed)}</p>
        {stoppage.startedBy && <p>Recorded by {stoppage.startedBy}.</p>}
        <p className="hmi-field-help">
          The line is not scheduled to produce. This time is in no target and is not planned or unplanned
          downtime. It ends when the next run is confirmed.
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onHome}>
            Home
          </button>
          <button type="button" className="hmi-primary-button" onClick={onStartNewRun}>
            Start Run
          </button>
        </div>
      </div>
    )
  }

  if (isRestartDelay) {
    return (
      <div className="hmi-screen hmi-line-stoppage">
        <h1>Restart delay — {stoppage.productionLine}</h1>
        <p className="hmi-planned-downtime__elapsed">Elapsed: {formatDuration(elapsed)}</p>
        <p>
          {stoppage.reason ? `“${stoppage.reason}” is resolved` : 'The stop is resolved'}
          {stoppage.startedBy ? ` (by ${stoppage.startedBy})` : ''}. The line is waiting to restart.
        </p>
        <p className="hmi-field-help">
          Unplanned downtime on the line, not charged to any run. It stops when the next run is confirmed.
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onHome}>
            Home
          </button>
          <button type="button" className="hmi-primary-button" onClick={onStartNewRun}>
            Start Run
          </button>
        </div>
      </div>
    )
  }

  // Handover, and a changeover in new-run setup, both stop only when the
  // next run is confirmed - there is nothing to "end" on this screen.
  if (isHandover || inSetup) {
    return (
      <div className="hmi-screen hmi-line-stoppage">
        {casepackerNotice}
        <h1>
          {isHandover ? 'Shift handover' : 'Changeover — new-run setup'} — {stoppage.productionLine}
        </h1>
        <p className="hmi-planned-downtime__elapsed">
          {isHandover ? 'Elapsed' : 'Total changeover'}: {formatDuration(elapsed)}
        </p>
        {inSetup && stoppage.physicalEndedAt && (
          <p>
            Physical work: {formatDuration(minutesBetween(stoppage.startedAt, new Date(stoppage.physicalEndedAt)))} ·
            New-run setup: {formatDuration(minutesBetween(stoppage.physicalEndedAt, now))}
          </p>
        )}
        {isHandover && stoppage.startedBy && <p>Handed over by {stoppage.startedBy}.</p>}
        <p className="hmi-field-help">
          {isHandover
            ? 'Planned downtime on the line, not charged to either run. It stops when the incoming technician confirms Start Run.'
            : 'Still timing. It stops when the new run details are confirmed and the run starts.'}
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onHome}>
            Home
          </button>
          <button type="button" className="hmi-primary-button" onClick={onStartNewRun} disabled={casepackerBlocked}>
            {isHandover ? 'Start Run (incoming technician)' : 'Enter New Run Details'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="hmi-screen hmi-line-stoppage">
      {casepackerNotice}
      <h1>
        {isChangeover ? 'Changeover' : 'Line stopped'} — {stoppage.productionLine}
      </h1>
      <p className="hmi-planned-downtime__elapsed">Elapsed: {formatDuration(elapsed)}</p>
      {!isChangeover && stoppage.reason && <p>Reason: {stoppage.reason}</p>}
      <p className="hmi-field-help">
        {isChangeover
          ? 'Planned downtime on the line. Press End Changeover when the physical work is done; the timer keeps running until the new run starts.'
          : 'Unplanned downtime on the line, not charged to any run. Resolve starts the restart delay, which runs until the next run is confirmed.'}
      </p>

      <label className="hmi-field">
        {isChangeover ? 'Ended by' : 'Resolved by'}
        <select value={endedBy} onChange={(e) => setEndedBy(e.target.value)}>
          <option value="">Select technician</option>
          {LINE_TECHNICIANS.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onHome} disabled={isSubmitting}>
          Home
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={() => onEnd(endedBy)}
          disabled={isSubmitting || !endedBy}
        >
          {isSubmitting ? 'Saving…' : isChangeover ? 'End Changeover' : 'Resolve'}
        </button>
      </div>
    </div>
  )
}
