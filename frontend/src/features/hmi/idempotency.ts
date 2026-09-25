/**
 * Idempotency for every HMI write.
 *
 * One logical action (this hourly update, this fault report, this
 * changeover) keeps ONE key from the moment the operator confirms it
 * until the backend accepts it or the operator deliberately cancels.
 * Retrying with that key makes the server replay its original response
 * instead of writing a second record (src/pulse_capture_api.py).
 *
 * The pending action is also written to localStorage, so a tablet that
 * is refreshed or closed mid-request can offer to finish the same
 * action with the same key instead of silently repeating it.
 */

const PENDING_KEY = 'pulse.hmi.pendingAction.v1'

export type PendingActionKind =
  | 'hourlyUpdate'
  | 'plannedDowntimeStart'
  | 'plannedDowntimeEnd'
  | 'faultReport'
  | 'changeoverStart'
  | 'changeoverComplete'
  | 'completeRun'

export interface PendingAction {
  kind: PendingActionKind
  key: string
  runId: number
  /** Shown to the operator if this action is still unconfirmed. */
  label: string
  payload: unknown
  createdAtIso: string
}

/** Backend requires 16-100 characters of [A-Za-z0-9_-]. */
export function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto

  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return `k-${cryptoApi.randomUUID().replace(/-/g, '')}`
  }

  if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16))
    return `k-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
  }

  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

export function loadPendingAction(): PendingAction | null {
  try {
    const raw = window.localStorage.getItem(PENDING_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PendingAction
    return parsed && typeof parsed.key === 'string' ? parsed : null
  } catch {
    return null
  }
}

export function savePendingAction(action: PendingAction): void {
  try {
    window.localStorage.setItem(PENDING_KEY, JSON.stringify(action))
  } catch {
    // Best effort: the in-memory key still protects this page session.
  }
}

export function clearPendingAction(): void {
  try {
    window.localStorage.removeItem(PENDING_KEY)
  } catch {
    // ignore
  }
}

/**
 * The key to use for `kind` right now: the existing pending key when
 * the operator is retrying the same action, otherwise a fresh one.
 * Reusing the key is what makes a retry safe; a NEW key is what makes
 * a genuinely new update (for example a second hourly update) count.
 */
export function beginAction(
  pending: PendingAction | null,
  kind: PendingActionKind,
  runId: number,
  label: string,
  payload: unknown,
): PendingAction {
  const reuseKey = pending && pending.kind === kind && pending.runId === runId ? pending.key : null

  const action: PendingAction = {
    kind,
    key: reuseKey ?? newIdempotencyKey(),
    runId,
    label,
    payload,
    createdAtIso: new Date().toISOString(),
  }

  savePendingAction(action)
  return action
}
