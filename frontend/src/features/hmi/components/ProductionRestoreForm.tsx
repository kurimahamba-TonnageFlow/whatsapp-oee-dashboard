import { useState } from 'react'
import { ApiRequestError } from '../../../api/client'
import { apiClient } from '../../../api/client'
import { newIdempotencyKey } from '../idempotency'
import type { LineFault } from '../types'

export function ProductionRestoreForm({ fault, line, technician, onRestored }: {
  fault: LineFault; line: string; technician: string; onRestored: () => void
}) {
  const [open, setOpen] = useState(false)
  const [time, setTime] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState<{ key: string; body: { production_line: string; technician: string; note: string; restored_at: string } } | null>(null)

  async function save() {
    if (busy) return
    if (!attempt && (!time || !note.trim() || !Number.isFinite(new Date(time).getTime()))) {
      setError('Enter the actual restart time and what was done.')
      return
    }
    const request = attempt ?? { key: newIdempotencyKey(), body: {
      production_line: line, technician, note: note.trim(), restored_at: new Date(time).toISOString(),
    } }
    setAttempt(request)
    setBusy(true)
    setError('')
    try {
      await apiClient.post(`/api/v1/faults/${fault.downtime_event_id}/production-restored`, request.body, { idempotencyKey: request.key })
      onRestored()
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : 'Restart was not confirmed. Retry with the same details.')
      if (cause instanceof ApiRequestError && cause.status >= 400 && cause.status < 500) setAttempt(null)
    } finally { setBusy(false) }
  }

  if (!open) return <button type="button" className="hmi-secondary-button" onClick={() => setOpen(true)}>Production restored</button>
  return <div>
    <p>Stop downtime for this fault. Engineering keeps its job open.</p>
    <label className="hmi-field">Actual restart time (tablet local time)
      <input type="datetime-local" value={time} disabled={busy || attempt !== null} onChange={(e) => setTime(e.target.value)} />
    </label>
    <label className="hmi-field">What was done?
      <textarea maxLength={500} value={note} disabled={busy || attempt !== null} onChange={(e) => setNote(e.target.value)} />
    </label>
    {error && <p role="alert">{error}</p>}
    <button type="button" className="hmi-primary-button" disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Confirm production restart'}</button>
    <button type="button" className="hmi-secondary-button" disabled={busy || attempt !== null} onClick={() => setOpen(false)}>Cancel</button>
  </div>
}
