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
  /** Resolves true when the list was actually re-read. A caller whose
   * write has already been confirmed needs to know this, so it can say
   * the list is stale rather than imply the write failed. */
  refresh: () => Promise<boolean>
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

  const load = useCallback(async (): Promise<boolean> => {
    if (!token) return false

    // A newer request always replaces whatever was still running.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    if (hasLoadedRef.current) {
      setIsRefreshing(true)
    }

    try {
      const response = await getFaults(token, controller.signal)
      if (controller.signal.aborted) return false

      setFaults(response.items)
      setLoadError(null)
      setRefreshError(null)
      setLastRefreshedAt(new Date())
      hasLoadedRef.current = true
      return true
    } catch (error: unknown) {
      if (controller.signal.aborted) return false

      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired()
        return false
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
      return false
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false)
        setIsRefreshing(false)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const refresh = useCallback(() => load(), [load])

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

    void load()

    function startInterval() {
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = setInterval(() => void load(), FAULT_POLL_INTERVAL_MS)
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
      void load()
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
