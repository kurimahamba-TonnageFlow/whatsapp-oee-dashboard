import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../../../api/client'
import { useManagementSession } from './useManagementSession'

export interface ProtectedData<T> {
  data: T | null
  /** True on the first load and while refreshing (data stays visible). */
  isLoading: boolean
  error: string | null
  loadedAt: Date | null
  reload: () => void
}

/** A read that has not answered by then is abandoned with a clear
 * message, so a stalled server never leaves the page loading forever. */
export const REQUEST_TIMEOUT_MS = 30_000

const TIMEOUT_MESSAGE = 'The Pulse server took too long to respond. Please try again.'

function safeLoadError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 0) return 'Could not reach the Pulse server. Check your connection and try again.'
    if (error.status >= 500) return 'The data is temporarily unavailable. Please try again shortly.'
    // FastAPI 4xx details are pre-written, safe sentences (docs/*_integration.md).
    return error.message
  }
  return 'The data could not be loaded. Please try again.'
}

/**
 * Loads data for a Management-protected page with the shared session
 * token. Re-loads whenever `key` changes (encode every filter in it) or
 * reload() is called; an in-flight request is aborted when superseded.
 * A 401 goes through the shared session-expiry flow (handleAuthError),
 * which returns the manager to sign-in - it is never shown as an error.
 */
export function useProtectedData<T>(
  load: (token: string, signal: AbortSignal) => Promise<T>,
  key: string,
): ProtectedData<T> {
  const { session, handleAuthError } = useManagementSession()
  const token = session?.token ?? null
  const loadRef = useRef(load)
  const [reloadCount, setReloadCount] = useState(0)
  const [state, setState] = useState<Omit<ProtectedData<T>, 'reload'>>({
    data: null,
    isLoading: true,
    error: null,
    loadedAt: null,
  })

  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    if (!token) return
    const controller = new AbortController()
    let timedOut = false
    const timer = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
    setState((previous) => ({ ...previous, isLoading: true, error: null }))

    loadRef
      .current(token, controller.signal)
      .then((data) => {
        window.clearTimeout(timer)
        if (controller.signal.aborted) return
        setState({ data, isLoading: false, error: null, loadedAt: new Date() })
      })
      .catch((error: unknown) => {
        window.clearTimeout(timer)
        if (timedOut) {
          setState((previous) => ({ ...previous, isLoading: false, error: TIMEOUT_MESSAGE }))
          return
        }
        if (controller.signal.aborted) return
        if (handleAuthError(error)) return
        setState((previous) => ({ ...previous, isLoading: false, error: safeLoadError(error) }))
      })

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [token, key, reloadCount, handleAuthError])

  const reload = useCallback(() => setReloadCount((count) => count + 1), [])

  return { ...state, reload }
}
