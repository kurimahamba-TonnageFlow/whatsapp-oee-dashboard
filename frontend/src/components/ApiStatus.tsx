import { useApiStatus, type ApiStatusState } from '../hooks/useApiStatus'

const LABELS: Record<ApiStatusState, string> = {
  loading: 'Checking API…',
  connected: 'API connected',
  unavailable: 'API unavailable',
}

export function ApiStatus() {
  const status = useApiStatus()

  return (
    <div className={`api-status api-status--${status}`} role="status">
      <span className="api-status__dot" aria-hidden="true" />
      {LABELS[status]}
    </div>
  )
}
