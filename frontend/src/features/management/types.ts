/** Confirmed contracts from src/management_api.py and
 * docs/management_integration.md. Nothing here is invented. */

export interface ManagementLoginPayload {
  pin: string
  manager_name: string
}

/** POST /api/v1/management/login - 200 response. `expires_at` is an
 * ISO-8601 UTC timestamp (sessions last 30 minutes by default). */
export interface ManagementLoginResponse {
  status: string
  token: string
  manager_name: string
  expires_at: string
}

/** POST /api/v1/management/logout - 200 response. */
export interface ManagementLogoutResponse {
  status: string
  message: string
}

/** GET /api/v1/management/session - 200 response. `expires_at` is the
 * expiry set at login; the check never extends it. */
export interface ManagementSessionResponse {
  status: string
  manager_name: string
  expires_at: string
}

/** The only management state the browser keeps - in React memory, and
 * in this tab's sessionStorage so a refresh does not sign the manager
 * out (session/sessionStore.ts). Never in localStorage, IndexedDB or a
 * cookie. The PIN is never part of it. */
export interface ManagementSession {
  token: string
  managerName: string
  expiresAt: string
}

/** The reasons src/management_api.py accepts, in its order. */
export const FORCE_CLOSE_REASONS = [
  'Technician left mid-shift',
  'Tablet or browser closed',
  'Run started by mistake',
  'Changeover completed',
  'Production stopped',
  'Duplicate run',
  'Other',
] as const

export type ForceCloseReason = (typeof FORCE_CLOSE_REASONS)[number]

/** GET /api/v1/management/active-runs - one item. */
export interface ActiveRun {
  id: number
  production_line: string
  line_technician: string
  shift: string
  customer: string | null
  product: string | null
  status: string
  started_at: string
  /** Seconds the run had been open when the server answered. */
  active_seconds: number
  last_hourly_update_at: string | null
  hourly_update_count: number
  open_planned_stop_reason: string | null
  open_planned_stop_started_at: string | null
  open_changeover_id: number | null
  /** Faults still open on the line, from any run - they carry over. */
  open_line_fault_count: number
}

export interface ActiveRunsResponse {
  items: ActiveRun[]
}

/** POST /api/v1/management/runs/{id}/force-close - body. `note` is
 * required when reason is 'Other'. */
export interface ForceCloseRequest {
  reason: ForceCloseReason
  note: string | null
}

/** POST /api/v1/management/runs/{id}/force-close - 200 response. */
export interface ForceCloseResponse {
  status: string
  run_id: number
  production_line: string
  run_status: string
  finished_at: string
  closed_by: string
  reason: string
  ended_planned_stop: { reason: string; started_at: string; ended_at: string } | null
}
