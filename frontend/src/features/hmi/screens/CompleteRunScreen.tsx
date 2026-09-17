import type { ActiveRunRecord } from '../types'

interface CompleteRunScreenProps {
  run: ActiveRunRecord
  isSubmitting: boolean
  errorMessage: string | null
  onCancel: () => void
  onConfirm: () => void
}

export function CompleteRunScreen({
  run,
  isSubmitting,
  errorMessage,
  onCancel,
  onConfirm,
}: CompleteRunScreenProps) {
  return (
    <div className="hmi-screen hmi-complete-run">
      <h1>Complete Run — {run.form.productionLine}</h1>
      <p className="hmi-inline-warning" role="alert">
        This will close the active run. This cannot be undone from the HMI.
      </p>

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
          onClick={onConfirm}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Completing…' : 'Confirm Complete Run'}
        </button>
      </div>
    </div>
  )
}
