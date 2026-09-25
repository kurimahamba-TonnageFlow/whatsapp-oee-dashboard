import { useCallback, useEffect, useRef, useState } from 'react'
import { getLineState } from './api'
import { LINE_STATE_POLL_INTERVAL_MS } from './constants'
import type { HmiLineState } from './types'

export type LineStateStatus =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; lines: HmiLineState[] }

interface UseLineStatePollingResult {
  lineState: LineStateStatus
  lastRefreshedAt: Date | null
  /** Re-reads immediately. Used by the Retry button and after a 409. */
  refresh: () => Promise<void>
}

/**
 * GET /api/v1/hmi/lines on an interval, so every tablet gets the same
 * answer to "is this line already running?".
 *
 * Same discipline as the Engineering fault poll:
 *   - immediate load on mount,
 *   - a fixed interval, paused while the tab is hidden and resumed with
 *     an immediate refresh when it becomes visible again (a tablet left
 *     face-down on a bench must not keep polling),
 *   - at most one request in flight - a newer request aborts whatever
 *     was still running, so responses cannot arrive out of order and two
 *     requests never overlap.
 *
 * A failure becomes `error`, never an empty line list: the Home screen
 * must not conclude a line is free because a request failed.
 */
export function useLineStatePolling(): UseLineStatePollingResult {
  const [lineState, setLineState] = useState<LineStateStatus>({ status: 'loading' })
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await getLineState(controller.signal)
      if (controller.signal.aborted) return
      setLineState({ status: 'ready', lines: response.lines })
      setLastRefreshedAt(new Date())
    } catch {
      if (controller.signal.aborted) return
      // Honest: state unknown, not "everything is available".
      setLineState({ status: 'error' })
    }
  }, [])

  useEffect(() => {
    void load()

    function startInterval() {
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = setInterval(() => void load(), LINE_STATE_POLL_INTERVAL_MS)
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        return
      }

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
  }, [load])

  return { lineState, lastRefreshedAt, refresh: load }
}
