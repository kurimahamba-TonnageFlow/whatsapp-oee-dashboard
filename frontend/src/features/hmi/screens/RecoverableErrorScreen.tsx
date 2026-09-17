interface RecoverableErrorScreenProps {
  message: string
  onRetry: () => void
  onBackToHome: () => void
}

export function RecoverableErrorScreen({
  message,
  onRetry,
  onBackToHome,
}: RecoverableErrorScreenProps) {
  return (
    <div className="hmi-screen hmi-recoverable-error" role="alert">
      <h1>Something went wrong</h1>
      <p>{message}</p>
      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onBackToHome}>
          Back to Home
        </button>
        <button type="button" className="hmi-primary-button" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  )
}
