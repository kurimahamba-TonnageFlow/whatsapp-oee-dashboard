interface RunCompletedScreenProps {
  productionLine: string
  onBackToHome: () => void
}

export function RunCompletedScreen({ productionLine, onBackToHome }: RunCompletedScreenProps) {
  return (
    <div className="hmi-screen hmi-run-completed" role="status">
      <p className="hmi-run-started__mark">✓ RUN COMPLETED</p>
      <p>{productionLine} is now available for a new run.</p>
      <div className="hmi-form-actions">
        <button type="button" className="hmi-primary-button" onClick={onBackToHome}>
          Back to Home
        </button>
      </div>
    </div>
  )
}
