import type { ManagementSession } from '../types'

/**
 * Keeps the Management session across a page refresh in THIS browser tab
 * only. sessionStorage is scoped to the tab and emptied by the browser
 * when the tab closes; nothing goes to localStorage, IndexedDB or a
 * cookie, and the PIN is never stored. A restored token is not trusted
 * until GET /api/v1/management/session confirms it (see
 * ManagementSessionProvider), so a revoked, expired or pre-restart token
 * only ever leads back to sign-in.
 */
const STORAGE_KEY = 'pulse.management.session.v1'

export function readStoredSession(): ManagementSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<ManagementSession>
    if (
      typeof value.token !== 'string' ||
      typeof value.managerName !== 'string' ||
      typeof value.expiresAt !== 'string'
    ) {
      clearStoredSession()
      return null
    }
    const expiresAtMs = Date.parse(value.expiresAt)
    if (Number.isNaN(expiresAtMs) || expiresAtMs <= Date.now()) {
      clearStoredSession()
      return null
    }
    return { token: value.token, managerName: value.managerName, expiresAt: value.expiresAt }
  } catch {
    return null
  }
}

export function storeSession(session: ManagementSession) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Storage blocked (private mode, policy): the session still works,
    // it just will not survive a refresh - the previous behaviour.
  }
}

export function clearStoredSession() {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing stored, or storage blocked - nothing to clear.
  }
}
