import { useEffect, useState } from 'react'
import { formatDuration } from '../progress'
import type { Changeover } from '../types'

interface ChangeoverCompleteScreenProps {
  changeover: Changeover
  isSubmitting: boolean
  errorMessage: string | null
  onCancel: () => void
  onComplete: () => void
}

export function ChangeoverCompleteScreen({
  changeover,
  isSubmitting,
  errorMessage,
  onCancel,
  onComplete,
}: ChangeoverCompleteScreenProps) {
  const [confirmed, setConfirmed] = useState(false)
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(interval)
  }, [])

  const elapsedMinutes = (now.getTime() - new Date(changeover.started_at).getTime()) / 60000

  return (
    <div className="hmi-screen hmi-changeover">
      <h1>Changeover in progress</h1>
      <p className="hmi-planned-downtime__elapsed">Elapsed: {formatDuration(elapsedMinutes)}</p>

      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>From</dt>
          <dd>
            {changeover.previous_customer} — {changeover.previous_product}
          </dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>To</dt>
          <dd>
            {changeover.new_customer} — {changeover.new_product}
          </dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>New pack weight</dt>
          <dd>{changeover.new_pack_weight_kg} kg</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>New format</dt>
          <dd>{changeover.new_format}</dd>
        </div>
      </dl>

      <label className="hmi-field hmi-field--checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          disabled={isSubmitting}
        />
        The first acceptable packs of the new run are being produced
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
          onClick={onComplete}
          disabled={isSubmitting || !confirmed}
        >
          {isSubmitting ? 'Completing…' : 'Changeover Complete'}
        </button>
      </div>
    </div>
  )
}
