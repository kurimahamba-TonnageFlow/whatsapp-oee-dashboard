/**
 * LIVE backend calls only. Every function here calls a confirmed, real
 * endpoint (docs/management_integration.md, src/management_api.py).
 */
import { apiClient } from '../../api/client'
import type {
  ManagementLoginPayload,
  ManagementLoginResponse,
  ManagementLogoutResponse,
  ManagementSessionResponse,
  ActiveRunsResponse,
  ForceCloseRequest,
  ForceCloseResponse,
} from './types'

/** POST /api/v1/management/login - no token required. */
export function login(payload: ManagementLoginPayload, signal?: AbortSignal) {
  return apiClient.post<ManagementLoginResponse>('/api/v1/management/login', payload, { signal })
}

/** POST /api/v1/management/logout - requires a bearer token. */
export function logout(token: string, signal?: AbortSignal) {
  return apiClient.post<ManagementLogoutResponse>('/api/v1/management/logout', undefined, {
    token,
    signal,
  })
}

/** GET /api/v1/management/session - confirms a token kept across a page
 * refresh is still live. Never extends the session. */
export function getSession(token: string, signal?: AbortSignal) {
  return apiClient.get<ManagementSessionResponse>('/api/v1/management/session', { token, signal })
}

/** GET /api/v1/management/active-runs - requires a bearer token. */
export function getActiveRuns(token: string, signal?: AbortSignal) {
  return apiClient.get<ActiveRunsResponse>('/api/v1/management/active-runs', { token, signal })
}

/** POST /api/v1/management/runs/{id}/force-close - requires a bearer
 * token. A second close of the same run is refused (409), so a retry
 * can never close anything twice. */
export function forceCloseRun(token: string, runId: number, body: ForceCloseRequest, signal?: AbortSignal) {
  return apiClient.post<ForceCloseResponse>(`/api/v1/management/runs/${runId}/force-close`, body, {
    token,
    signal,
  })
}
