import { useEffect, useState } from 'react'
import type { HourlyUpdateResult } from '../awaitingApiIntegration'
import type { ActiveRunRecord } from '../types'

interface HourlyUpdateScreenProps {
  run: ActiveRunRecord
  isSubmitting: boolean
  result: HourlyUpdateResult | null
  errorMessage: string | null
  onCancel: () => void
  onSubmit: (palletsProducedThisPeriod: number) => void
  onDone: () => void
}

const AUTO_RETURN_MS = 1600

export function HourlyUpdateScreen({
  run,
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
            <dt>Previous total</dt>
            <dd>{result.previousTotal} pallets</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>New total</dt>
            <dd>{result.newTotal} pallets</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Pallets produced this period</dt>
            <dd>{result.palletsProducedThisPeriod}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Updated pallets remaining</dt>
            <dd>{result.palletsRemaining}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Expected output</dt>
            <dd>{Math.round(result.expectedPacksThisPeriod)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Actual output</dt>
            <dd>{Math.round(result.actualPacksThisPeriod)} packs</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Updated output gap</dt>
            <dd>{Math.round(result.outputGapPacks)} packs</dd>
          </div>
        </dl>
      </div>
    )
  }

  function handleSubmit() {
    const value = Number(palletsProduced)
    if (palletsProduced.trim() === '' || !Number.isFinite(value) || value < 0) {
      setValidationError('Enter a number of pallets, 0 or more.')
      return
    }
    setValidationError(null)
    onSubmit(value)
  }

  return (
    <div className="hmi-screen hmi-hourly-update">
      <h1>Hourly Update — {run.form.productionLine}</h1>

      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>Previous total</dt>
          <dd>{run.totalPalletsCompleted} pallets</dd>
        </div>
      </dl>

      <label className="hmi-field">
        Pallets produced this period
        <input
          type="number"
          inputMode="numeric"
          min={0}
          step="1"
          value={palletsProduced}
          onChange={(e) => setPalletsProduced(e.target.value)}
          disabled={isSubmitting}
        />
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
