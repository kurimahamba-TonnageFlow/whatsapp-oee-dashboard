import type { StoredActiveRun } from './types'

// v2: only the run id and line. A v1 record (which cached form values
// and totals on the device) is deliberately ignored - saved progress
// now always comes from the backend.
const STORAGE_KEY = 'pulse.hmi.activeRun.v2'

/**
 * Remembers ONLY which run this tablet is working on, so a refresh can
 * ask the backend for its current state
 * (GET /api/v1/runs/{id}/hmi-state). Production totals, planned
 * downtime and changeovers are never restored from here - they are
 * always re-read from the database, so this device can never show
 * saved progress the server does not have.
 */
export function loadActiveRun(): StoredActiveRun | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredActiveRun
    return typeof parsed?.runId === 'number' ? parsed : null
  } catch {
    return null
  }
}

export function saveActiveRun(record: StoredActiveRun): void {
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
