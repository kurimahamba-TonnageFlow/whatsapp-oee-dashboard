import { useState } from 'react'
import type { RunState, TargetSpeedChange } from '../types'

interface TargetSpeedScreenProps {
  state: RunState
  isSubmitting: boolean
  errorMessage: string | null
  onCancel: () => void
  onSubmit: (newSpeed: string, reason: string, effectiveAt?: string, supersedesId?: number) => void
}

function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' })
}

/** Operating observations and append-only corrections; the agreed standard never changes. */
export function TargetSpeedScreen({ state, isSubmitting, errorMessage, onCancel, onSubmit }: TargetSpeedScreenProps) {
  const [speed, setSpeed] = useState('')
  const [reason, setReason] = useState('')
  const [effective, setEffective] = useState('')
  const [correction, setCorrection] = useState<number | undefined>()
  const [errors, setErrors] = useState<{ speed?: string; reason?: string }>({})
  const history = state.operating_speed_changes ?? []
  const superseded = new Set(history.map(change => change.supersedes_id).filter(id => id != null))

  function correct(change: TargetSpeedChange) {
    setCorrection(change.change_id ?? undefined)
    setSpeed(String(change.new_speed_ppm))
    setReason('')
    const at = new Date(change.effective_at)
    setEffective(new Date(at.getTime() - at.getTimezoneOffset() * 60000).toISOString().slice(0, 16))
  }

  function handleSubmit() {
    const next: typeof errors = {}
    if (effective && !Number.isFinite(new Date(effective).getTime())) next.reason = "Enter a valid effective time."
    const value = Number(speed.trim())
    if (!speed.trim() || !Number.isFinite(value) || value < 0) next.speed = 'Enter an operating speed of 0 or more.'
    if (!reason.trim()) next.reason = 'Write why the operating setting is changing.'
    setErrors(next)
    if (Object.keys(next).length === 0) onSubmit(speed.trim(), reason.trim(), effective ? new Date(effective).toISOString() : undefined, correction)
  }

  return (
    <div className="hmi-screen hmi-target-speed">
      <h1>Record Operating Speed — {state.run.production_line}</h1>
      <p>
        Agreed standard: <strong>{state.run.standard_speed_ppm ?? 'Unknown (legacy run)'} packs/min</strong>.
        Recording a setting never lowers this production baseline. Unrecorded settings remain unknown.
      </p>

      <label className="hmi-field">
        Operating speed (packs/min)
        <input type="text" inputMode="decimal" value={speed} onChange={(e) => setSpeed(e.target.value)} />
        {errors.speed && (
          <span className="hmi-field-error" role="alert">
            {errors.speed}
          </span>
        )}
      </label>

      <label className="hmi-field">
        Effective time (blank means changed now; shown in this device's timezone)
        <input type="datetime-local" value={effective} onChange={e => setEffective(e.target.value)} />
      </label>
      <label className="hmi-field">
        Reason for the change
        <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        {errors.reason && (
          <span className="hmi-field-error" role="alert">
            {errors.reason}
          </span>
        )}
      </label>

      {history.length > 0 && (
        <dl className="hmi-review-list" aria-label="Recorded operating settings">
          {history.map((change) => (
            <div key={change.change_id ?? change.effective_at} className="hmi-review-list__row">
              <dt>{clockTime(change.effective_at)}</dt>
              <dd>
                {change.previous_speed_ppm ?? 'Unknown'} → {change.new_speed_ppm} packs/min · {change.changed_by} ·{' '}
                {change.reason}
                {change.submitted_at && <span> Submitted {clockTime(change.submitted_at)}</span>}
                <button type="button" disabled={isSubmitting || superseded.has(change.change_id ?? -1)}
                  onClick={() => correct(change)}>
                  {superseded.has(change.change_id ?? -1) ? 'Superseded (history retained)' : 'Correct this record'}
                </button>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {correction && <p>Correction to record {correction}. Enter its correct effective time. The original stays in history.</p>}
      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel} disabled={isSubmitting}>
          Back
        </button>
        <button type="button" className="hmi-primary-button" onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : 'Save Operating Speed'}
        </button>
      </div>
    </div>
  )
}
