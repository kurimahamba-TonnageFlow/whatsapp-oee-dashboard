import type { StartRunFormValues } from '../types'

interface ReviewRunScreenProps {
  values: StartRunFormValues
  isSubmitting: boolean
  errorMessage: string | null
  onBack: () => void
  onConfirm: () => void
}

const ROWS: Array<[label: string, field: keyof StartRunFormValues]> = [
  ['Production line', 'productionLine'],
  ['Line technician', 'lineTechnician'],
  ['Shift', 'shift'],
  ['Customer', 'customer'],
  ['Product', 'product'],
  ['Pack weight', 'packWeightLabel'],
  ['Pack weight (kg)', 'packWeightKg'],
  ['Packs per case', 'packsPerCase'],
  ['Format', 'packType'],
  ['Target speed (packs/min)', 'targetSpeedPpm'],
  ['Cases per pallet', 'casesPerPallet'],
  ['Pallets remaining', 'palletsRemaining'],
  ['Previous run completed', 'previousRunCompleted'],
]

export function ReviewRunScreen({
  values,
  isSubmitting,
  errorMessage,
  onBack,
  onConfirm,
}: ReviewRunScreenProps) {
  return (
    <div className="hmi-screen hmi-review-run">
      <h1>Review Run</h1>

      <dl className="hmi-review-list">
        {ROWS.map(([label, field]) => (
          <div key={field} className="hmi-review-list__row">
            <dt>{label}</dt>
            <dd>{values[field] || '—'}</dd>
          </div>
        ))}
      </dl>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button
          type="button"
          className="hmi-secondary-button"
          onClick={onBack}
          disabled={isSubmitting}
        >
          Back
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={onConfirm}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Starting Run…' : 'Confirm Start Run'}
        </button>
      </div>
    </div>
  )
}
