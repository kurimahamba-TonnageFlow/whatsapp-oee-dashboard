import type { ActiveRunRecord } from './types'

const STORAGE_KEY = 'pulse.hmi.activeRun.v1'

/**
 * This-device-only persistence for the run currently in progress.
 * There is no live "get active run" endpoint the public HMI can call
 * (see docs/hmi_integration.md - only the PIN-protected Management
 * API has one, and this stage must not use it), so this local record
 * is what lets a page refresh restore the Active Run screen instead
 * of losing track of it (requirement: refreshing must not falsely
 * show a completed action). It reflects a real, API-confirmed Start
 * Run - it is not a fixture.
 */
export function loadActiveRun(): ActiveRunRecord | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as ActiveRunRecord
  } catch {
    return null
  }
}

export function saveActiveRun(record: ActiveRunRecord): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
  } catch {
    // Best-effort only - if storage is unavailable, the Active Run
    // screen still works for the current page session, it just won't
    // survive a refresh.
  }
}

export function clearActiveRun(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}
