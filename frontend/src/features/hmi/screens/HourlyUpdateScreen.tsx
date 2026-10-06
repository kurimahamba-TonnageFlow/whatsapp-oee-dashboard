import { HourlyShareCard } from '../components/HourlyShareCard'
import { OperatingContext } from '../../shared/OperatingContext'
import { useState } from 'react'
import { reviewHourlyLoss, type HourlyLossReview } from '../api'
import { ProductionRestoreForm } from '../components/ProductionRestoreForm'
import { validatePalletsInput } from '../validation'
import type { HourlyUpdateResponse, RunHour, RunState } from '../types'

interface HourlyUpdateScreenProps {
  state: RunState
  isSubmitting: boolean
  result: HourlyUpdateResponse | null
  errorMessage: string | null
  onCancel: () => void
  onSubmit: (hour: RunHour, palletsProduced: string, lossReason: string) => void
  /** After a saved reading: the next due hour, or back to the run. */
  onDone: () => void
  onFaultRestored?: () => void
}

function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/London',
  })
}

/**
 * Fixed clock hours: each reading is for ONE named hour (06:00–07:00),
 * normally entered just after it ends. Missed hours are asked for one
 * at a time, oldest first - one pallet count is never spread across
 * several hours.
 */
export function HourlyUpdateScreen({
  state,
  isSubmitting,
  result,
  errorMessage,
  onCancel,
  onSubmit,
  onDone,
  onFaultRestored,
}: HourlyUpdateScreenProps) {
  const [palletsProduced, setPalletsProduced] = useState('')
  const [lossReason, setLossReason] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)
  const [review, setReview] = useState<{ hour: string; pallets: string; result: HourlyLossReview } | null>(null)

  const hours = state.hours
  const due = (hours?.hours ?? []).filter((hour) => hour.status === 'due')
  const hour = due[0] ?? null

  if (result) {
    const remaining = due.filter((item) => item.hour_start !== result.hour_start).length
    return (
      <div className="hmi-screen hmi-hourly-update" role="status">
        <p className="hmi-run-started__mark">✓ {result.hour_label} recorded</p>
        <dl className="hmi-review-list">
          <div className="hmi-review-list__row">
            <dt>Pallets this hour</dt>
            <dd>{result.pallets_produced}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Target for this hour</dt>
            <dd>{Math.round(result.expected_packs)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Actual this hour</dt>
            <dd>{Math.round(result.actual_packs)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Output vs target (all stops)</dt>
            <dd>
              {result.production_achievement_percent === null ? '—' : `${result.production_achievement_percent}%`}
            </dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Pallets remaining</dt>
            <dd>{result.pallets_remaining}</dd>
          </div>
        </dl>
        {result.loss_review && <div role="status">
          <p>Remaining gap: {result.loss_review.remaining_gap_packs ?? 'Unknown'} packs
            ({result.loss_review.equivalent_minutes ?? '—'} equivalent production minutes, not measured downtime).</p>
          {result.loss_review.limitations?.map(message => <p key={message}>{message}</p>)}
        </div>}
        <HourlyShareCard key={result.hourly_update_id} run={state.run} result={result} />
        <div className="hmi-form-actions">
          <button
            type="button"
            className="hmi-primary-button"
            onClick={() => {
              setPalletsProduced('')
              setLossReason('')
              setReview(null)
              onDone()
            }}
          >
            {remaining > 0 ? `Next missed hour (${remaining} left)` : 'Back to the run'}
          </button>
        </div>
      </div>
    )
  }

  if (!hour) {
    const current = hours?.current_hour
    return (
      <div className="hmi-screen hmi-hourly-update">
        <h1>Hourly Update — {state.run.production_line}</h1>
        <p className="hmi-inline-warning" role="status">
          {current
            ? `No hour is waiting. ${current.hour_label} can be reported after it ends at ${clockTime(current.hour_end)}.`
            : 'No hour is waiting to be reported.'}
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onCancel}>
            Back
          </button>
        </div>
      </div>
    )
  }

  async function handleSubmit() {
    if (!hour || checking || isSubmitting) return
    const error = validatePalletsInput(palletsProduced)
    if (error) {
      setValidationError(error)
      return
    }
    setValidationError(null)
    if (review?.hour === hour.hour_start && review.pallets === palletsProduced.trim()) {
      if (review.result.prompt_required && !lossReason.trim()) {
        setValidationError('Explain the remaining loss, or choose Cause unknown.')
        return
      }
      onSubmit(hour, palletsProduced.trim(), lossReason.trim())
      return
    }
    setChecking(true)
    try {
      const result = await reviewHourlyLoss(state.run.run_id, {
        line_technician: state.run.line_technician,
        hour_start: hour.hour_start,
        pallets_produced: palletsProduced.trim(),
      })
      setReview({ hour: hour.hour_start, pallets: palletsProduced.trim(), result })
      if (!result.prompt_required) onSubmit(hour, palletsProduced.trim(), lossReason.trim())
    } catch {
      setValidationError('Could not check the output gap. Nothing has been submitted. Try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="hmi-screen hmi-hourly-update">
      <h1>Hourly Update — {state.run.production_line}</h1>

      {(state.line_faults ?? []).length > 0 && (
        <section aria-label="Check production restart">
          <h2>Has production restarted?</h2>
          <p>Record the actual restart time for each restored fault, even if it was earlier than this report.</p>
          {(state.line_faults ?? []).map((fault) => <div key={fault.downtime_event_id}>
            <p>{fault.machine} — {fault.reason}</p>
            <ProductionRestoreForm fault={fault} line={state.run.production_line} technician={state.run.line_technician} onRestored={() => { setReview(null); (onFaultRestored ?? onCancel)() }} />
          </div>)}
        </section>
      )}

      {due.length > 1 && (
        <p className="hmi-inline-warning" role="alert">
          {due.length} hours have not been reported. Enter each hour separately, starting with the
          earliest.
        </p>
      )}

      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>Hour</dt>
          <dd>
            <strong>{hour.hour_label}</strong>
            {hour.is_partial_hour && ` (${hour.applicable_minutes} min of this run)`}
          </dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets so far this run</dt>
          <dd>{state.run.total_pallets_completed}</dd>
        </div>
      </dl>

      <label className="hmi-field">
        Pallets produced {hour.hour_label}
        <input
          type="text"
          inputMode="decimal"
          value={palletsProduced}
          onChange={(e) => { setPalletsProduced(e.target.value); setReview(null) }}
          disabled={isSubmitting || checking}
          aria-describedby="hmi-hourly-help"
        />
        <span id="hmi-hourly-help" className="hmi-field-help">
          Only the pallets made in this hour - whole or part pallets, for example 3.75. Enter 0 if
          nothing was produced.
        </span>
        {validationError && (
          <span className="hmi-field-error" role="alert">
            {validationError}
          </span>
        )}
      </label>

      {review?.hour === hour.hour_start && <p>
        Fixed standard target: {review.result.target_packs ?? 'Unknown'} packs.
        Raw stop equivalents: planned {review.result.raw_planned_packs ?? '—'}, unplanned {review.result.raw_unplanned_packs ?? '—'} packs.
        These are estimates, not confirmed causes.
      </p>}
      {review?.hour === hour.hour_start && <OperatingContext reports={review.result.operating_context} />}
      {review?.hour === hour.hour_start && review.result.prompt_required && (
        <div className="hmi-inline-warning" role="status">
          <p>Recorded stops do not account for all the output gap. About <strong>{review.result.equivalent_minutes} minutes</strong> of equivalent production remains unexplained.</p>
          <p>This is an estimate at the management standard, not additional recorded downtime. Add the cause below, or leave it unknown.</p>
          <button type="button" className="hmi-secondary-button" disabled={isSubmitting || checking} onClick={() => onSubmit(hour, palletsProduced.trim(), '')}>Cause unknown — save reading</button>
        </div>
      )}

      <label className="hmi-field">
        Other output loss this hour (optional)
        <textarea
          value={lossReason}
          onChange={(e) => setLossReason(e.target.value)}
          rows={3}
          maxLength={500}
          disabled={isSubmitting || checking}
          aria-describedby="hmi-loss-help"
        />
        <span id="hmi-loss-help" className="hmi-field-help">
          Explain slow running, small stops or waiting not covered by a recorded stop.
          Leave blank if the cause is unknown. This note does not create a downtime event.
        </span>
      </label>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel} disabled={isSubmitting || checking}>
          Back
        </button>
        <button type="button" className="hmi-primary-button" onClick={() => void handleSubmit()} disabled={isSubmitting || checking}>
          {checking ? 'Checking output…' : isSubmitting ? 'Saving…' : `Save ${hour.hour_label}`}
        </button>
      </div>
    </div>
  )
}
