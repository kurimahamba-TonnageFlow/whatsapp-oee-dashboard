import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { ApiRequestError } from '../../../api/client'
import * as managementApi from '../api'
import type { ManagementLoginResponse, ManagementSession } from '../types'
import {
  ManagementSessionContext,
  SESSION_EXPIRED_MESSAGE,
  SIGNED_OUT_MESSAGE,
  type ManagementSessionContextValue,
  type SessionEndReason,
} from './managementSessionContext'
import { clearStoredSession, readStoredSession, storeSession } from './sessionStore'

/** Largest delay setTimeout honours (about 24.8 days). */
const MAX_TIMER_DELAY_MS = 2 ** 31 - 1

const RESTORE_UNAVAILABLE_MESSAGE =
  'Could not check your Management session with the Pulse server. Please sign in again.'

/** Best-effort server-side revocation. The in-memory and stored session
 * are cleared by the caller regardless of whether this request succeeds. */
function revokeHeldToken(tokenRef: RefObject<string | null>) {
  const token = tokenRef.current
  tokenRef.current = null
  if (token) {
    clearStoredSession()
    managementApi.logout(token).catch(() => {})
  }
}

/**
 * Owns the Management session shared by /management,
 * /management/performance and /dashboard.
 *
 * The session lives in this component's React state and in this tab's
 * sessionStorage (sessionStore.ts), so a browser refresh keeps the
 * manager signed in. On a refresh the stored token is shown as
 * "checking" until GET /api/v1/management/session confirms it with the
 * server; a revoked, expired or pre-restart token goes back to sign-in.
 * The PIN is never kept, nothing reaches localStorage, IndexedDB or a
 * cookie, and closing the tab forgets the token. Leaving the Management
 * area (which unmounts this provider) still ends the session and
 * revokes the token server-side, so a shared factory tablet is never
 * left holding a live Management session.
 *
 * Sessions live in the API process's memory: a restart signs every
 * manager out, and the API must run as ONE worker process or a token
 * issued by one worker is unknown to the others.
 */
export function ManagementSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<ManagementSession | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [endReason, setEndReason] = useState<SessionEndReason>(null)
  // A token kept from before a refresh, waiting for the server to confirm it.
  const [pending, setPending] = useState<ManagementSession | null>(readStoredSession)
  const tokenRef = useRef<string | null>(null)

  const expireSession = useCallback((message: string = SESSION_EXPIRED_MESSAGE) => {
    // The server already treats this token as invalid - nothing to revoke.
    tokenRef.current = null
    clearStoredSession()
    setSession(null)
    setEndReason('expired')
    setNotice(message)
  }, [])

  const signIn = useCallback((response: ManagementLoginResponse) => {
    const signedIn = {
      token: response.token,
      managerName: response.manager_name,
      expiresAt: response.expires_at,
    }
    tokenRef.current = response.token
    storeSession(signedIn)
    setPending(null)
    setNotice(null)
    setEndReason(null)
    setSession(signedIn)
  }, [])

  // After a refresh: trust the stored token only once the server confirms
  // it. The server's name and expiry win over what the tab stored.
  const pendingToken = pending?.token ?? null
  useEffect(() => {
    if (!pendingToken) return
    const controller = new AbortController()
    managementApi
      .getSession(pendingToken, controller.signal)
      .then((confirmed) => {
        if (controller.signal.aborted) return
        const restored = {
          token: pendingToken,
          managerName: confirmed.manager_name,
          expiresAt: confirmed.expires_at,
        }
        tokenRef.current = pendingToken
        storeSession(restored)
        setSession(restored)
        setPending(null)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        clearStoredSession()
        setPending(null)
        const rejected = error instanceof ApiRequestError && error.status === 401
        setEndReason('expired')
        setNotice(rejected ? SESSION_EXPIRED_MESSAGE : RESTORE_UNAVAILABLE_MESSAGE)
      })
    return () => controller.abort()
  }, [pendingToken])

  const signOut = useCallback(() => {
    revokeHeldToken(tokenRef)
    clearStoredSession()
    setSession(null)
    setEndReason('signed_out')
    setNotice(SIGNED_OUT_MESSAGE)
  }, [])

  const acknowledgeSignOut = useCallback(() => {
    setEndReason((reason) => (reason === 'signed_out' ? null : reason))
  }, [])

  const handleAuthError = useCallback(
    (error: unknown) => {
      if (error instanceof ApiRequestError && error.status === 401) {
        expireSession()
        return true
      }
      return false
    },
    [expireSession],
  )

  // Return to login automatically at the server's expiry time. A 401
  // from any protected call (handleAuthError) covers clock skew.
  useEffect(() => {
    if (!session) return
    const expiresAtMs = Date.parse(session.expiresAt)
    if (Number.isNaN(expiresAtMs)) return

    // setTimeout fires immediately for delays above 2^31-1 ms, so a
    // long deadline is waited out in capped steps, re-checking the
    // clock each time rather than trusting a single long timer.
    let timer: number | undefined
    const check = () => {
      const remainingMs = expiresAtMs - Date.now()
      if (remainingMs <= 0) {
        expireSession()
        return
      }
      timer = window.setTimeout(check, Math.min(remainingMs, MAX_TIMER_DELAY_MS))
    }
    check()
    return () => window.clearTimeout(timer)
  }, [session, expireSession])

  // Leaving the Management area ends the session server-side too.
  useEffect(() => () => revokeHeldToken(tokenRef), [])

  const value = useMemo<ManagementSessionContextValue>(
    () => ({
      session,
      isRestoring: pending !== null,
      endReason,
      notice,
      signIn,
      signOut,
      expireSession,
      acknowledgeSignOut,
      handleAuthError,
    }),
    [session, pending, endReason, notice, signIn, signOut, expireSession, acknowledgeSignOut, handleAuthError],
  )

  return <ManagementSessionContext.Provider value={value}>{children}</ManagementSessionContext.Provider>
}
