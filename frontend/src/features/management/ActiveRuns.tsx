import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError } from '../../api/client'
import { formatDateTime } from '../dashboard/format'
import * as managementApi from './api'
import { useManagementSession } from './session/useManagementSession'
import { useProtectedData } from './session/useProtectedData'
import { FORCE_CLOSE_REASONS, type ActiveRun, type ForceCloseReason, type ForceCloseResponse } from './types'

/** "3 h 05 min", "2 d 4 h" - how long a run has been open. */
function formatRunDuration(totalSeconds: number): string {
  const minutes = Math.max(0, Math.floor(totalSeconds / 60))
  const days = Math.floor(minutes / (60 * 24))
  const hours = Math.floor((minutes % (60 * 24)) / 60)
  const mins = minutes % 60
  if (days > 0) return `${days} d ${hours} h`
  if (hours > 0) return `${hours} h ${String(mins).padStart(2, '0')} min`
  return `${mins} min`
}

function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`
}

function closeErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 0 || error.status >= 500) {
      return 'Could not confirm whether the run was closed. Refresh Active runs and check its status before trying again.'
    }
    // 404/409/422 details are pre-written, safe sentences from the server.
    return error.message
  }
  return 'Could not confirm whether the run was closed. Refresh Active runs and check its status before trying again.'
}

/**
 * Management > Active runs. Lists every run still open and lets a
 * manager close one that was abandoned (tablet closed, technician gone)
 * with a recorded reason, after a confirmation that spells out what
 * happens: the run ends now as Cancelled, unreported hours stay missing,
 * an open planned stop is ended, open faults stay with the line, and the
 * line then needs its next step recorded.
 */
export function ActiveRuns() {
  const runs = useProtectedData((token, signal) => managementApi.getActiveRuns(token, signal), 'active-runs')
  const [closing, setClosing] = useState<ActiveRun | null>(null)
  const [closed, setClosed] = useState<ForceCloseResponse | null>(null)
  const [now, setNow] = useState(() => Date.now())

  // Durations tick on screen without re-reading the server.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const loadedAtMs = runs.loadedAt?.getTime() ?? now
  const items = runs.data?.items ?? []

  return (
    <section className="management-active-runs" aria-labelledby="active-runs-heading">
      <p className="management-eyebrow">
        <Link to="/management">Management</Link>
      </p>
      <h1 id="active-runs-heading">Active runs</h1>
      <p className="management-muted">
        Every run still open on a line. Force-close only a run that nobody will finish on the tablet — for example
        the tablet was closed or the technician has left.
      </p>

      {closed && (
        <div className="management-notice" role="status">
          <p>
            <strong>
              Run {closed.run_id} on {closed.production_line} was force-closed
            </strong>{' '}
            ({closed.reason}). It is recorded in the management audit log under your name.
          </p>
          {closed.ended_planned_stop && (
            <p>The open planned stop “{closed.ended_planned_stop.reason}” was ended at the same time.</p>
          )}
          <p>
            {closed.production_line} now needs its next step recorded before a new run can start — by the next
            technician on the tablet, or on the <Link to="/dashboard">Production dashboard</Link> under “Run
            ended — next step not chosen”.
          </p>
        </div>
      )}

      {runs.error && (
        <p className="management-alert" role="alert">
          {runs.error}
        </p>
      )}

      {runs.isLoading && !runs.data && <p className="management-muted">Loading active runs…</p>}

      {runs.data && items.length === 0 && (
        <p className="management-panel management-muted">No runs are active on any line.</p>
      )}

      {items.length > 0 && (
        <div className="management-table-wrap">
          <table className="management-table">
            <caption className="management-visually-hidden">Runs in progress</caption>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col">Technician</th>
                <th scope="col">Started</th>
                <th scope="col">Running for</th>
                <th scope="col">Output last reported</th>
                <th scope="col">Open on this line</th>
                <th scope="col">
                  <span className="management-visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((run) => (
                <tr key={run.id}>
                  <th scope="row">{run.production_line}</th>
                  <td>{run.line_technician}</td>
                  <td>{formatDateTime(run.started_at)}</td>
                  <td>{formatRunDuration(run.active_seconds + (now - loadedAtMs) / 1000)}</td>
                  <td>{run.last_hourly_update_at ? formatDateTime(run.last_hourly_update_at) : 'Not yet'}</td>
                  <td>
                    <OpenItems run={run} />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="management-secondary-button"
                      onClick={() => {
                        setClosed(null)
                        setClosing(run)
                      }}
                      aria-label={`Force close the run on ${run.production_line}`}
                      disabled={closing !== null}
                    >
                      Force close…
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {closing && (
        <ForceCloseForm
          key={closing.id}
          run={closing}
          onCancel={() => setClosing(null)}
          onClosed={(response) => {
            setClosing(null)
            setClosed(response)
            runs.reload()
          }}
        />
      )}
    </section>
  )
}

function OpenItems({ run }: { run: ActiveRun }) {
  const parts: string[] = []
  if (run.open_line_fault_count > 0) parts.push(plural(run.open_line_fault_count, 'open fault', 'open faults'))
  if (run.open_planned_stop_reason) parts.push(`Planned stop: ${run.open_planned_stop_reason}`)
  if (run.open_changeover_id !== null) parts.push('Changeover in progress')
  return <>{parts.length ? parts.join(' · ') : 'Nothing open'}</>
}

type Step = 'reason' | 'confirm'

function ForceCloseForm({
  run,
  onCancel,
  onClosed,
}: {
  run: ActiveRun
  onCancel: () => void
  onClosed: (response: ForceCloseResponse) => void
}) {
  const { session, handleAuthError } = useManagementSession()
  const [step, setStep] = useState<Step>('reason')
  const [reason, setReason] = useState<ForceCloseReason | ''>('')
  const [note, setNote] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const noteRequired = reason === 'Other'
  const changeoverOpen = run.open_changeover_id !== null

  function review(event: FormEvent) {
    event.preventDefault()
    if (!reason) {
      setProblem('Choose why this run is being closed.')
      return
    }
    if (noteRequired && !note.trim()) {
      setProblem('Write a note explaining the reason.')
      return
    }
    setProblem(null)
    setStep('confirm')
  }

  async function confirm() {
    if (!session || !reason) return
    setSubmitting(true)
    setProblem(null)
    try {
      const response = await managementApi.forceCloseRun(session.token, run.id, {
        reason,
        note: note.trim() ? note.trim() : null,
      })
      onClosed(response)
    } catch (error) {
      if (handleAuthError(error)) return
      setProblem(closeErrorMessage(error))
      setSubmitting(false)
    }
  }

  const headingId = `force-close-${run.id}`

  return (
    <section className="management-panel management-force-close" aria-labelledby={headingId}>
      <h2 id={headingId}>
        Force close the run on {run.production_line} — {run.line_technician}, started{' '}
        {formatDateTime(run.started_at)}
      </h2>

      {changeoverOpen ? (
        <>
          <p className="management-alert" role="alert">
            A changeover is in progress on this run. Complete it on the {run.production_line} tablet (Changeover
            Complete) first — a changeover cannot be abandoned from here.
          </p>
          <div className="management-actions">
            <button type="button" className="management-secondary-button" onClick={onCancel}>
              Back
            </button>
          </div>
        </>
      ) : step === 'reason' ? (
        <form onSubmit={review} noValidate>
          <fieldset className="management-choices">
            <legend>Why is this run being closed?</legend>
            {FORCE_CLOSE_REASONS.map((option) => (
              <label key={option} className="management-choice">
                <input
                  type="radio"
                  name={`force-close-reason-${run.id}`}
                  value={option}
                  checked={reason === option}
                  onChange={() => setReason(option)}
                />
                {option}
              </label>
            ))}
          </fieldset>
          <label className="management-field">
            {noteRequired ? 'Note (required for Other)' : 'Note (optional)'}
            <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={500} />
          </label>
          {problem && (
            <p className="management-alert" role="alert">
              {problem}
            </p>
          )}
          <div className="management-actions">
            <button type="submit" className="management-primary-button">
              Continue
            </button>
            <button type="button" className="management-secondary-button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div>
          <p>
            <strong>Reason:</strong> {reason}
            {note.trim() ? ` — ${note.trim()}` : ''}
          </p>
          <ul className="management-consequences" aria-label="What force-closing does">
            <li>
              The run ends <strong>now</strong> and is marked <strong>Cancelled</strong>. It is not deleted: its
              reported hours, faults and history stay as they are.
            </li>
            <li>
              Nothing is added for hours nobody reported
              {run.hourly_update_count > 0
                ? ` (${plural(run.hourly_update_count, 'hour was', 'hours were')} reported)`
                : ' (no hours were reported)'}
              . They stay as missing output — never estimated.
            </li>
            {run.open_planned_stop_reason && (
              <li>
                The open planned stop “{run.open_planned_stop_reason}” (since{' '}
                {formatDateTime(run.open_planned_stop_started_at)}) is ended at the same time.
              </li>
            )}
            <li>
              {run.open_line_fault_count > 0 ? (
                <>
                  The {plural(run.open_line_fault_count, 'open fault', 'open faults')} on {run.production_line}{' '}
                  {run.open_line_fault_count === 1 ? 'stays' : 'stay'} open. Faults belong to the line, not the run:
                  Engineering still sees them, and the next technician must acknowledge them before starting a run.
                </>
              ) : (
                <>There are no open faults on {run.production_line}. Any reported later will carry over as usual.</>
              )}
            </li>
            <li>
              {run.production_line} then needs its next step recorded (End Shift, Changeover, Other or Not
              scheduled) before a new run can start — by the next technician on the tablet, or on the Production
              dashboard.
            </li>
            <li>Your name, the reason and the run as it was are written to the management audit log.</li>
          </ul>
          {problem && (
            <p className="management-alert" role="alert">
              {problem}
            </p>
          )}
          <div className="management-actions">
            <button
              type="button"
              className="management-danger-button"
              onClick={confirm}
              disabled={submitting}
            >
              {submitting ? 'Closing…' : `Force close run on ${run.production_line}`}
            </button>
            <button
              type="button"
              className="management-secondary-button"
              onClick={() => setStep('reason')}
              disabled={submitting}
            >
              Back
            </button>
            <button type="button" className="management-secondary-button" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
