import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { HealthResponse } from '../types/api'

export type ApiStatusState = 'loading' | 'connected' | 'unavailable'

/** Calls GET /health once on mount and reports connection state. The
 * page renders regardless of the result - this never throws. */
export function useApiStatus(): ApiStatusState {
  const [status, setStatus] = useState<ApiStatusState>('loading')

  useEffect(() => {
    const controller = new AbortController()

    apiClient
      .get<HealthResponse>('/health', { signal: controller.signal })
      .then(() => {
        if (!controller.signal.aborted) {
          setStatus('connected')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setStatus('unavailable')
        }
      })

    return () => controller.abort()
  }, [])

  return status
}
