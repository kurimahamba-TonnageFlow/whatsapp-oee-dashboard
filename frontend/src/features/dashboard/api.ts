/**
 * LIVE backend calls only - every function calls a confirmed, real
 * endpoint (docs/dashboard_integration.md, src/dashboard_api.py). All
 * require a Management session token.
 */
import { apiClient } from '../../api/client'
import type { HmiLineStateResponse, LineStoppageResponse } from '../hmi/types'
import type {
  ChangeoverGroupBy,
  ChangeoversResponse,
  DashboardFaultsResponse,
  DashboardFilterOptions,
  DashboardOverview,
  DashboardRunsResponse,
  DashboardWindow,
  EngineeringClassificationResponse,
  HourlyReport,
  LineStopKind,
  LineStopLog,
  MachinesResponse,
  WeeklyTargetsResponse,
} from './types'

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** GET /api/v1/dashboard/overview - site/line output, gap attribution and line summaries. */
export function getOverview(
  token: string,
  params: { window: DashboardWindow; production_line?: string | null },
  signal?: AbortSignal,
) {
  return apiClient.get<DashboardOverview>(`/api/v1/dashboard/overview${query(params)}`, {
    token,
    signal,
  })
}

/** GET /api/v1/dashboard/runs - newest first, with each run's output. */
export function getRuns(
  token: string,
  params: {
    date_from?: string | null
    date_to?: string | null
    production_line?: string | null
    technician?: string | null
    shift?: string | null
    customer?: string | null
    product?: string | null
    page_size?: number
  },
  signal?: AbortSignal,
) {
  return apiClient.get<DashboardRunsResponse>(`/api/v1/dashboard/runs${query(params)}`, {
    token,
    signal,
  })
}

/** GET /api/v1/dashboard/filter-options - values present in the data. */
export function getFilterOptions(token: string, signal?: AbortSignal) {
  return apiClient.get<DashboardFilterOptions>('/api/v1/dashboard/filter-options', {
    token,
    signal,
  })
}

type WindowParams = { window: DashboardWindow; production_line?: string | null }

/** GET /api/v1/dashboard/weekly-targets - site and per-line weekly
 * progress. `week_start` must be a Monday; omitted = current week. */
export function getWeeklyTargets(token: string, weekStart: string | null, signal?: AbortSignal) {
  return apiClient.get<WeeklyTargetsResponse>(
    `/api/v1/dashboard/weekly-targets${query({ week_start: weekStart })}`,
    { token, signal },
  )
}

/** GET /api/v1/dashboard/machines - per-machine faults, downtime and
 * estimated tonnes lost, ranked worst first. */
export function getMachines(token: string, params: WindowParams, signal?: AbortSignal) {
  return apiClient.get<MachinesResponse>(`/api/v1/dashboard/machines${query(params)}`, {
    token,
    signal,
  })
}

/** GET /api/v1/dashboard/engineering-classification - faults by status,
 * repair classification and maintenance preventability. */
export function getEngineeringClassification(
  token: string,
  params: WindowParams,
  signal?: AbortSignal,
) {
  return apiClient.get<EngineeringClassificationResponse>(
    `/api/v1/dashboard/engineering-classification${query(params)}`,
    { token, signal },
  )
}

/** GET /api/v1/dashboard/faults - the fault register, newest first. */
export function getFaults(
  token: string,
  params: {
    date_from?: string | null
    date_to?: string | null
    production_line?: string | null
    machine?: string | null
    engineer?: string | null
    fault_status?: string | null
  },
  signal?: AbortSignal,
) {
  return apiClient.get<DashboardFaultsResponse>(`/api/v1/dashboard/faults${query(params)}`, {
    token,
    signal,
  })
}

/** GET /api/v1/dashboard/changeovers - the QC changeover list, optionally grouped. */
export function getChangeovers(
  token: string,
  params: {
    date_from?: string | null
    date_to?: string | null
    production_line?: string | null
    customer?: string | null
    product?: string | null
    status?: string | null
    group_by?: ChangeoverGroupBy | null
  },
  signal?: AbortSignal,
) {
  return apiClient.get<ChangeoversResponse>(`/api/v1/dashboard/changeovers${query(params)}`, {
    token,
    signal,
  })
}

/** GET /api/v1/dashboard/hourly - each line's clock hours for one shift. */
export function getHourly(
  token: string,
  params: { shift_offset: number; production_line?: string | null },
  signal?: AbortSignal,
) {
  return apiClient.get<HourlyReport>(`/api/v1/dashboard/hourly${query(params)}`, { token, signal })
}

/** GET /api/v1/hmi/lines - which lines have a run ended with no next step chosen. */
export function getLineDecisions(token: string, signal?: AbortSignal) {
  return apiClient.get<HmiLineStateResponse>('/api/v1/hmi/lines', { token, signal })
}

export type NextStepKind = 'handover' | 'changeover' | 'other' | 'not_scheduled'

/** POST /api/v1/lines/{line}/next-step/manager - an authorised manager
 * records what happened after a run whose End Run choice was never made. */
export function resolveNextStep(
  token: string,
  productionLine: string,
  payload: { kind: NextStepKind; reason: string | null },
  idempotencyKey: string,
) {
  return apiClient.post<LineStoppageResponse>(
    `/api/v1/lines/${encodeURIComponent(productionLine)}/next-step/manager`,
    payload,
    { token, idempotencyKey },
  )
}

/** GET /api/v1/dashboard/line-stops - between-run stops, their corrections
 * and the corrections still allowed. */
export function getLineStops(token: string, params: { days?: number } = {}, signal?: AbortSignal) {
  return apiClient.get<LineStopLog>(`/api/v1/dashboard/line-stops${query(params)}`, { token, signal })
}

/** POST /api/v1/line-stoppages/{id}/reclassify - a manager corrects a
 * stop's classification; the previous and new classification, who, when
 * and why are kept in the audit trail. */
export function reclassifyLineStop(
  token: string,
  stoppageId: number,
  payload: { new_kind: LineStopKind; reason: string | null; note: string },
  idempotencyKey: string,
) {
  return apiClient.post<LineStoppageResponse>(`/api/v1/line-stoppages/${stoppageId}/reclassify`, payload, {
    token,
    idempotencyKey,
  })
}

export function getLive(token:string,weekStart:string|null,signal?:AbortSignal){
 return apiClient.get<import('./liveTypes').LiveSnapshot>(`/api/v1/dashboard/live${query({week_start:weekStart})}`,{token,signal})
}
export function saveLiveTarget(token:string,payload:{site:'site';week_start:string;week_start_day:number;target_tonnes:number;notes:string}){
 return apiClient.post('/api/v1/management/live-weekly-target',payload,{token})
}
