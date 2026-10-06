import { useRef, useState } from 'react'
import { ApiRequestError } from '../../api/client'
import { newIdempotencyKey } from '../hmi/idempotency'
import { useManagementSession } from '../management/session/useManagementSession'
import { useProtectedData } from '../management/session/useProtectedData'
import * as dashboardApi from './api'
import { formatDateTime } from './format'
import type { LineStopKind, LineStopLogEntry, LineStopReclassification } from './types'
import { Panel } from './ui/Panel'
import { EmptyState, ErrorState, LoadingState } from './ui/states'

const KIND_LABEL: Record<LineStopKind, string> = {
  handover: 'Handover',
  changeover: 'Changeover',
  other: 'Other',
  restart_delay: 'Restart delay',
  not_scheduled: 'Not scheduled',
}

function describe(kind: LineStopKind, reason: string | null): string {
  return reason && kind !== 'handover' ? `${KIND_LABEL[kind]}: ${reason}` : KIND_LABEL[kind]
}

function minutesText(value: number): string {
  const hours = Math.floor(value / 60)
  const rest = Math.round(value % 60)
  return hours > 0 ? `${hours} h ${String(rest).padStart(2, '0')} min` : `${rest} min`
}

/** Between-run line stops from the last 7 days. A manager can correct a
 * late or wrong classification (e.g. Other -> Not scheduled); the stop
 * stays one interval, reports recalculate from the corrected row, and
 * every change is listed with who, when and why. */
export function LineStopCorrections({ onCorrected }: { onCorrected: () => void }) {
  const log = useProtectedData((token, signal) => dashboardApi.getLineStops(token, { days: 7 }, signal), 'line-stops')
  const [editing, setEditing] = useState<number | null>(null)
  const stops = log.data?.stops ?? []

  return (
    <Panel title="Line stops between runs — last 7 days">
      <p className="pd-footnote">
        Correct a stop that was recorded as the wrong kind. The time itself never moves; only its classification
        changes, and every report is recalculated from it. Each correction is kept with who made it, when and why.
      </p>
      {!log.data && log.isLoading && <LoadingState>Loading line stops…</LoadingState>}
      {!log.data && !log.isLoading && log.error && <ErrorState message={log.error} onRetry={log.reload} />}
      {log.data && stops.length === 0 && <EmptyState>No line stops between runs in the last 7 days.</EmptyState>}
      {stops.length > 0 && (
        <ul className="pd-stop-log">
          {stops.map((stop) => (
            <li key={stop.stoppage_id} className="pd-stop-log__item" aria-label={`Line stop ${stop.stoppage_id}`}>
              <div className="pd-stop-log__row">
                <span className="pd-stop-log__line">{stop.production_line}</span>
                <span className={`pd-hour__kind pd-hour__kind--${stop.downtime_type}`}>
                  {describe(stop.kind, stop.reason)}
                </span>
                <span className="pd-muted">
                  {formatDateTime(stop.started_at)} → {stop.is_open ? 'still open' : formatDateTime(stop.ended_at)} ·{' '}
                  {minutesText(stop.minutes)} · by {stop.started_by}
                </span>
                {stop.allowed_reclassifications.length > 0 && editing !== stop.stoppage_id && (
                  <button type="button" className="pd-text-button" onClick={() => setEditing(stop.stoppage_id)}>
                    Correct
                  </button>
                )}
              </div>
              {stop.reclassifications.length > 0 && (
                <ol className="pd-stop-log__history" aria-label={`Corrections to line stop ${stop.stoppage_id}`}>
                  {stop.reclassifications.map((change) => (
                    <HistoryItem key={change.reclassification_id} change={change} />
                  ))}
                </ol>
              )}
              {editing === stop.stoppage_id && (
                <CorrectionForm
                  stop={stop}
                  onCancel={() => setEditing(null)}
                  onSaved={() => {
                    setEditing(null)
                    log.reload()
                    onCorrected()
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function HistoryItem({ change }: { change: LineStopReclassification }) {
  return (
    <li>
      Changed from <strong>{describe(change.previous_kind, change.previous_reason)}</strong> to{' '}
      <strong>{describe(change.new_kind, change.new_reason)}</strong> by {change.changed_by},{' '}
      {formatDateTime(change.changed_at)} — “{change.note}”
    </li>
  )
}

function CorrectionForm({
  stop,
  onCancel,
  onSaved,
}: {
  stop: LineStopLogEntry
  onCancel: () => void
  onSaved: () => void
}) {
  const { session, handleAuthError } = useManagementSession()
  const choices = stop.allowed_reclassifications
  const [kind, setKind] = useState<LineStopKind>(choices.find((choice) => choice !== stop.kind) ?? choices[0])
  const [reason, setReason] = useState(stop.kind === 'other' ? (stop.reason ?? '') : '')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // One key per logical correction, reused on every retry until it succeeds.
  const keyRef = useRef<{ fingerprint: string; key: string } | null>(null)

  function submit() {
    if (!session || saving) return
    if (kind === 'other' && !reason.trim()) {
      setError('Write the reason the line was stopped.')
      return
    }
    if (!note.trim()) {
      setError('Say why this correction is being made.')
      return
    }
    const payload = { new_kind: kind, reason: kind === 'other' ? reason.trim() : null, note: note.trim() }
    const fingerprint = JSON.stringify(payload)
    if (keyRef.current?.fingerprint !== fingerprint) keyRef.current = { fingerprint, key: newIdempotencyKey() }

    setSaving(true)
    setError(null)
    dashboardApi
      .reclassifyLineStop(session.token, stop.stoppage_id, payload, keyRef.current.key)
      .then(() => {
        keyRef.current = null
        onSaved()
      })
      .catch((failure: unknown) => {
        if (handleAuthError(failure)) return
        setError(
          failure instanceof ApiRequestError && failure.status < 500 && failure.status !== 0
            ? failure.message
            : 'Could not save this to Pulse. Nothing was changed - please try again.',
        )
      })
      .finally(() => setSaving(false))
  }

  return (
    <div className="pd-decision pd-stop-log__form">
      <label className="pd-inline-field">
        <span>Correct to</span>
        <select value={kind} onChange={(event) => setKind(event.target.value as LineStopKind)}>
          {choices.map((choice) => (
            <option key={choice} value={choice}>
              {KIND_LABEL[choice]}
            </option>
          ))}
        </select>
      </label>
      {kind === 'other' && (
        <label className="pd-inline-field pd-decision__reason">
          <span>Reason</span>
          <input type="text" value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      )}
      <label className="pd-inline-field pd-decision__reason">
        <span>Why the change</span>
        <input type="text" value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <button type="button" className="pd-button" onClick={submit} disabled={saving}>
        {saving ? 'Saving…' : 'Save correction'}
      </button>
      <button type="button" className="pd-text-button" onClick={onCancel} disabled={saving}>
        Cancel
      </button>
      {error && (
        <p className="pd-error-text" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
