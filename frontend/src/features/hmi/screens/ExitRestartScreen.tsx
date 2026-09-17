interface ExitRestartScreenProps {
  productionLine: string
  onCancel: () => void
  onConfirmExit: () => void
}

/**
 * The HMI has no endpoint to force-close a run (that is a Management
 * action, deliberately not used here), so "Exit" can only mean: stop
 * tracking this run on this device. The run itself stays genuinely
 * Active in the system until someone completes or force-closes it -
 * this is explained plainly rather than implying the run is cancelled.
 */
export function ExitRestartScreen({
  productionLine,
  onCancel,
  onConfirmExit,
}: ExitRestartScreenProps) {
  return (
    <div className="hmi-screen hmi-exit-restart">
      <h1>Exit or Restart Run — {productionLine}</h1>
      <p className="hmi-inline-warning" role="alert">
        This run will stay active in the system - it will not be completed, cancelled or
        deleted. This only clears it from this tablet, so a manager or another tablet can
        still see and manage it. To close it properly, use Complete Run instead.
      </p>

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel}>
          Back
        </button>
        <button type="button" className="hmi-primary-button" onClick={onConfirmExit}>
          Exit to Home
        </button>
      </div>
    </div>
  )
}
