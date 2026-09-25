import { useEffect, useState } from 'react'
import { validatePalletsInput } from '../validation'
import type { HourlyUpdateResponse, RunState } from '../types'

interface HourlyUpdateScreenProps {
  state: RunState
  isSubmitting: boolean
  result: HourlyUpdateResponse | null
  errorMessage: string | null
  onCancel: () => void
  onSubmit: (palletsProduced: string) => void
  onDone: () => void
}

const AUTO_RETURN_MS = 1600

export function HourlyUpdateScreen({
  state,
  isSubmitting,
  result,
  errorMessage,
  onCancel,
  onSubmit,
  onDone,
}: HourlyUpdateScreenProps) {
  const [palletsProduced, setPalletsProduced] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    if (!result) return
    const timer = setTimeout(onDone, AUTO_RETURN_MS)
    return () => clearTimeout(timer)
  }, [result, onDone])

  if (result) {
    return (
      <div className="hmi-screen hmi-hourly-update" role="status">
        <p className="hmi-run-started__mark">✓ Update recorded</p>
        <dl className="hmi-review-list">
          <div className="hmi-review-list__row">
            <dt>Pallets produced this period</dt>
            <dd>{result.pallets_produced}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>New total</dt>
            <dd>{result.total_pallets_completed} pallets</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Updated pallets remaining</dt>
            <dd>{result.pallets_remaining}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Period</dt>
            <dd>{result.period_minutes} min</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Expected output</dt>
            <dd>{Math.round(result.expected_packs)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Actual output</dt>
            <dd>{Math.round(result.actual_packs)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Output gap</dt>
            <dd>{Math.round(result.output_gap_packs)} packs</dd>
          </div>
        </dl>
      </div>
    )
  }

  function handleSubmit() {
    const error = validatePalletsInput(palletsProduced)
    if (error) {
      setValidationError(error)
      return
    }
    setValidationError(null)
    onSubmit(palletsProduced.trim())
  }

  return (
    <div className="hmi-screen hmi-hourly-update">
      <h1>Hourly Update — {state.run.production_line}</h1>

      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>Previous total</dt>
          <dd>{state.run.total_pallets_completed} pallets</dd>
        </div>
      </dl>

      <label className="hmi-field">
        Pallets produced this period
        <input
          type="text"
          inputMode="decimal"
          value={palletsProduced}
          onChange={(e) => setPalletsProduced(e.target.value)}
          disabled={isSubmitting}
          aria-describedby="hmi-hourly-help"
        />
        <span id="hmi-hourly-help" className="hmi-field-help">
          Whole or part pallets, for example 3.75. Enter 0 if nothing was produced.
        </span>
        {validationError && (
          <span className="hmi-field-error" role="alert">
            {validationError}
          </span>
        )}
      </label>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button
          type="button"
          className="hmi-secondary-button"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Back
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={handleSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Saving…' : 'Confirm Update'}
        </button>
      </div>
    </div>
  )
}
