import { createContext } from 'react'
import type { ManagementLoginResponse, ManagementSession } from '../types'

export const SESSION_EXPIRED_MESSAGE = 'Your Management session has expired. Please sign in again.'
export const SIGNED_OUT_MESSAGE = 'You have signed out of Management.'

/** Why the last session ended - null until one has ended. */
export type SessionEndReason = 'expired' | 'signed_out' | null

export interface ManagementSessionContextValue {
  /** The signed-in manager's session, or null when signed out. */
  session: ManagementSession | null
  /** True after a refresh while the server confirms the session this
   * tab kept - show a "checking" state, not the sign-in screen. */
  isRestoring: boolean
  /** A deliberate sign-out never sends the manager back to the page
   * they left; an expiry does, once they sign in again. */
  endReason: SessionEndReason
  /** A one-off message for the login screen (expired / signed out). */
  notice: string | null
  /** Store the session returned by POST /api/v1/management/login. */
  signIn: (response: ManagementLoginResponse) => void
  /** Revoke the session server-side (best effort) and forget it. */
  signOut: () => void
  /** Forget the session because the server says it is no longer valid. */
  expireSession: (message?: string) => void
  /** Called once the sign-in screen is showing after a sign-out, so a
   * later visit to a protected page is remembered again. */
  acknowledgeSignOut: () => void
  /** For protected API calls: returns true (and expires the session) if
   * `error` is a 401, so the caller can stop instead of retrying. */
  handleAuthError: (error: unknown) => boolean
}

export const ManagementSessionContext = createContext<ManagementSessionContextValue | null>(null)
