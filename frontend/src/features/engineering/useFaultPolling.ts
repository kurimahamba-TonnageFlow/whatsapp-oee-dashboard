import { useCallback, useEffect, useRef, useState } from 'react'
import { getFaults } from './api'
import { ApiRequestError } from '../../api/client'
import { FAULT_POLL_INTERVAL_MS } from './constants'
import type { EngineeringFault } from './types'

interface UseFaultPollingResult {
  faults: EngineeringFault[]
  /** True only until the very first successful (or failed) load. */
  isLoading: boolean
  /** True while a refresh is in flight after the first load - existing
   * data stays on screen, this only drives a small, non-blocking indicator. */
  isRefreshing: boolean
  /** Set only when there is NO data to show at all (initial load failed). */
  loadError: string | null
  /** Set when a background refresh fails but earlier data remains visible. */
  refreshError: string | null
  lastRefreshedAt: Date | null
  refresh: () => void
}

/**
 * GET /api/v1/engineering/faults on an interval, with:
 *   - immediate load on mount
 *   - a 30s interval, paused while the tab is hidden and resumed (with
 *     an immediate refresh) when it becomes visible again
 *   - at most one request in flight: a newer request (manual or timer)
 *     aborts whatever was still running, so results can never arrive
 *     out of order and no two requests ever overlap
 *   - a 401 stops polling and hands off to onSessionExpired, exactly
 *     once, without retrying the now-invalid request
 */
export function useFaultPolling(
  token: string | null,
  onSessionExpired: () => void,
): UseFaultPollingResult {
  const [faults, setFaults] = useState<EngineeringFault[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const hasLoadedRef = useRef(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(() => {
    if (!token) return

    // A newer request always replaces whatever was still running.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    if (hasLoadedRef.current) {
      setIsRefreshing(true)
    }

    getFaults(token, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return
        setFaults(response.items)
        setLoadError(null)
        setRefreshError(null)
        setLastRefreshedAt(new Date())
        hasLoadedRef.current = true
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return

        if (error instanceof ApiRequestError && error.status === 401) {
          onSessionExpired()
          return
        }

        const message =
          error instanceof ApiRequestError
            ? error.message
            : 'Could not load Engineering faults. Please try again.'

        if (hasLoadedRef.current) {
          setRefreshError(message)
        } else {
          setLoadError(message)
        }
      })
      .finally(() => {
        if (controller.signal.aborted) return
        setIsLoading(false)
        setIsRefreshing(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const refresh = useCallback(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!token) {
      abortRef.current?.abort()
      if (intervalRef.current) clearInterval(intervalRef.current)
      hasLoadedRef.current = false
      setFaults([])
      setIsLoading(true)
      setIsRefreshing(false)
      setLoadError(null)
      setRefreshError(null)
      setLastRefreshedAt(null)
      return
    }

    load()

    function startInterval() {
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = setInterval(load, FAULT_POLL_INTERVAL_MS)
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        return
      }

      // Became visible again - refresh immediately, then resume polling.
      load()
      startInterval()
    }

    startInterval()
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (intervalRef.current) clearInterval(intervalRef.current)
      abortRef.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return { faults, isLoading, isRefreshing, loadError, refreshError, lastRefreshedAt, refresh }
}
