import type { OperatingReport } from '../shared/OperatingContext'
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

export interface HourlyLossReview {
  target_packs: number | null
  remaining_gap_packs: number | null
  equivalent_minutes: number | null
  raw_planned_packs?: number | null
  raw_unplanned_packs?: number | null
  operating_context?: OperatingReport[]
  excess_modelled_packs?: number | null
  limitations?: string[]
  prompt_required: boolean
}

export function reviewHourlyLoss(runId: number, payload: HourlyUpdatePayload) {
  return apiClient.post<HourlyLossReview>(`/api/v1/runs/${runId}/hourly-loss-review`, payload)
}
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
  FaultAcknowledgePayload,
  HourlyUpdatePayload,
  HourlyUpdateResponse,
  LineStoppageResponse,
  LineStoppageStartPayload,
  OpenLineFaultsResponse,
  PlannedDowntimeEndPayload,
  PlannedDowntimeResponse,
  PlannedDowntimeStartPayload,
  RunHours,
  RunState,
  StartRunPayload,
  StartRunResponse,
  TargetSpeedChange,
  TargetSpeedPayload,
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

/** GET /api/v1/runs/{run_id}/hours - every clock hour of the run, with
 * which are reported, due (each missed hour asked for on its own) or
 * in progress. */
export function getRunHours(runId: number, signal?: AbortSignal) {
  return apiClient.get<RunHours & { production_run_id: number }>(`/api/v1/runs/${runId}/hours`, { signal })
}

/** Operating-speed evidence, including retrospective records and corrections. */
export function changeTargetSpeed(
  runId: number,
  payload: TargetSpeedPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<TargetSpeedChange & { status: string }>(
    `/api/v1/runs/${runId}/operating-speed`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/lines/{line}/stoppages - Changeover or Other, after End Run. */
export function startLineStoppage(
  productionLine: string,
  payload: LineStoppageStartPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<LineStoppageResponse>(
    `/api/v1/lines/${encodeURIComponent(productionLine)}/stoppages`,
    payload,
    { idempotencyKey, signal },
  )
}

/** POST /api/v1/line-stoppages/{id}/end - End Changeover / Resolve. */
export function endLineStoppage(
  stoppageId: number,
  payload: { ended_by: string },
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<LineStoppageResponse>(`/api/v1/line-stoppages/${stoppageId}/end`, payload, {
    idempotencyKey,
    signal,
  })
}

/** GET /api/v1/lines/{line}/open-faults - faults still open on the line. */
export function getOpenLineFaults(productionLine: string, signal?: AbortSignal) {
  return apiClient.get<OpenLineFaultsResponse>(
    `/api/v1/lines/${encodeURIComponent(productionLine)}/open-faults`,
    { signal },
  )
}

/** POST /api/v1/faults/{id}/acknowledge - acknowledge AND escalate the
 * existing fault; never creates another. */
export function acknowledgeFault(
  downtimeEventId: number,
  payload: FaultAcknowledgePayload,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return apiClient.post<{ status: string; escalated: boolean; downtime_event_id: number; escalation_count: number }>(
    `/api/v1/faults/${downtimeEventId}/acknowledge`,
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
