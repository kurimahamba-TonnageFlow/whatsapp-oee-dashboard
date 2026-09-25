/**
 * LIVE backend calls only. Every function here calls a confirmed, real
 * endpoint (docs/hmi_integration.md, src/hmi_config_api.py,
 * src/runs_api.py, src/pulse_capture_api.py). No endpoint is invented,
 * and no manufacturing figure is calculated here - the backend returns
 * every number this screen shows.
 *
 * Each write takes the idempotency key for its logical action; the same
 * key must be reused for every retry of that action.
 */
import { apiClient } from '../../api/client'
import type { HealthResponse, HmiConfigResponse } from '../../types/api'
import type {
  ChangeoverCompletePayload,
  ChangeoverPairResponse,
  ChangeoverStartPayload,
  CompleteRunResponse,
  CompletionPayload,
  CompletionPreviewResponse,
  FaultReportPayload,
  FaultReportResponse,
  HmiLineStateResponse,
  HourlyUpdatePayload,
  HourlyUpdateResponse,
  PlannedDowntimeEndPayload,
  PlannedDowntimeResponse,
  PlannedDowntimeStartPayload,
  RunState,
  StartRunPayload,
  StartRunResponse,
} from './types'

export function getHealth(signal?: AbortSignal) {
  return apiClient.get<HealthResponse>('/health', { signal })
}

/** GET /api/v1/hmi/config - active lines/machines/buttons only. */
export function getHmiConfig(signal?: AbortSignal) {
  return apiClient.get<HmiConfigResponse>('/api/v1/hmi/config', { signal })
}

/** GET /api/v1/hmi/lines - authoritative cross-device line state. This
 * is what decides whether a line can be started, not local storage. */
export function getLineState(signal?: AbortSignal) {
  return apiClient.get<HmiLineStateResponse>('/api/v1/hmi/lines', { signal })
}

/** GET /api/v1/runs/{run_id}/hmi-state - authoritative active-run state. */
export function getRunState(runId: number, signal?: AbortSignal) {
  return apiClient.get<RunState>(`/api/v1/runs/${runId}/hmi-state`, { signal })
}

/** POST /api/v1/runs */
export function startRun(payload: StartRunPayload, idempotencyKey: string, signal?: AbortSignal) {
  return apiClient.post<StartRunResponse>('/api/v1/runs', payload, { idempotencyKey, signal })
}

/** POST /api/v1/runs/{run_id}/hourly-updates */
export function submitHourlyUpdate(
  runId: number,
  payload: HourlyUpdatePayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<HourlyUpdateResponse>(
    `/api/v1/runs/${runId}/hourly-updates`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/runs/{run_id}/planned-downtime */
export function startPlannedDowntime(
  runId: number,
  payload: PlannedDowntimeStartPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<PlannedDowntimeResponse>(
    `/api/v1/runs/${runId}/planned-downtime`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/planned-downtime/{id}/end */
export function endPlannedDowntime(
  plannedDowntimeId: number,
  payload: PlannedDowntimeEndPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<PlannedDowntimeResponse>(
    `/api/v1/planned-downtime/${plannedDowntimeId}/end`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/runs/{run_id}/faults */
export function reportFault(
  runId: number,
  payload: FaultReportPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<FaultReportResponse>(`/api/v1/runs/${runId}/faults`, payload, {
    idempotencyKey,
    signal,
  })
}

/** POST /api/v1/runs/{run_id}/changeovers - starts the planned stop and
 * the structured changeover record together. */
export function startChangeover(
  runId: number,
  payload: ChangeoverStartPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<ChangeoverPairResponse>(`/api/v1/runs/${runId}/changeovers`, payload, {
    idempotencyKey,
    signal,
  })
}

/** POST /api/v1/changeovers/{id}/complete - completes the changeover and
 * ends its planned stop together. */
export function completeChangeover(
  changeoverId: number,
  payload: ChangeoverCompletePayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<ChangeoverPairResponse>(
    `/api/v1/changeovers/${changeoverId}/complete`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/runs/{run_id}/completion-preview - read-only; the
 * backend calculates the review figures, nothing is saved. */
export function previewCompletion(
  runId: number,
  payload: CompletionPayload,
  signal?: AbortSignal,
) {
  return apiClient.post<CompletionPreviewResponse>(
    `/api/v1/runs/${runId}/completion-preview`,
    payload,
    { signal },
  )
}

/** POST /api/v1/runs/{run_id}/complete - final production, X-ray record
 * and run closure in one transaction. */
export function completeRun(
  runId: number,
  payload: CompletionPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<CompleteRunResponse>(`/api/v1/runs/${runId}/complete`, payload, {
    idempotencyKey,
    signal,
  })
}
