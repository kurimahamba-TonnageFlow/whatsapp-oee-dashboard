/**
 * LIVE backend calls only. Every function here calls a confirmed,
 * real endpoint (docs/hmi_integration.md, src/hmi_config_api.py,
 * src/runs_api.py). No endpoint here is invented.
 */
import { apiClient } from '../../api/client'
import type { HealthResponse, HmiConfigResponse } from '../../types/api'
import type { CompleteRunResponse, StartRunPayload, StartRunResponse } from './types'

export function getHealth(signal?: AbortSignal) {
  return apiClient.get<HealthResponse>('/health', { signal })
}

/** GET /api/v1/hmi/config - active lines/machines/buttons only. */
export function getHmiConfig(signal?: AbortSignal) {
  return apiClient.get<HmiConfigResponse>('/api/v1/hmi/config', { signal })
}

/** POST /api/v1/runs */
export function startRun(payload: StartRunPayload, signal?: AbortSignal) {
  return apiClient.post<StartRunResponse>('/api/v1/runs', payload, { signal })
}

/** POST /api/v1/runs/{run_id}/complete */
export function completeRun(runId: number, signal?: AbortSignal) {
  return apiClient.post<CompleteRunResponse>(`/api/v1/runs/${runId}/complete`, undefined, {
    signal,
  })
}
