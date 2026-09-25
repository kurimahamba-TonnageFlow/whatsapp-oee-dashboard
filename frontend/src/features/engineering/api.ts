/**
 * LIVE backend calls only. Every function here calls a confirmed,
 * real endpoint (docs/engineering_integration.md, src/engineering_api.py).
 * No endpoint here is invented.
 */
import { apiClient } from '../../api/client'
import type {
  CloseFaultPayload,
  EngineeringAcceptResponse,
  EngineeringCloseResponse,
  EngineeringFaultsResponse,
  EngineeringHandoverResponse,
  EngineeringLoginPayload,
  EngineeringLoginResponse,
  EngineeringUpdateResponse,
  HandoverPayload,
  RepairUpdatePayload,
} from './types'

/** POST /api/v1/engineering/login - no token required. */
export function login(payload: EngineeringLoginPayload, signal?: AbortSignal) {
  return apiClient.post<EngineeringLoginResponse>('/api/v1/engineering/login', payload, { signal })
}

/** POST /api/v1/engineering/logout - requires a bearer token. */
export function logout(token: string, signal?: AbortSignal) {
  return apiClient.post<{ status: string; message: string }>(
    '/api/v1/engineering/logout',
    undefined,
    { token, signal },
  )
}

/** GET /api/v1/engineering/faults - requires a bearer token. */
export function getFaults(token: string, signal?: AbortSignal) {
  return apiClient.get<EngineeringFaultsResponse>('/api/v1/engineering/faults', { token, signal })
}

/** POST /api/v1/engineering/faults/{id}/accept - no request body. */
export function acceptFault(token: string, downtimeEventId: number, signal?: AbortSignal) {
  return apiClient.post<EngineeringAcceptResponse>(
    `/api/v1/engineering/faults/${downtimeEventId}/accept`,
    undefined,
    { token, signal },
  )
}

/** POST /api/v1/engineering/faults/{id}/updates */
export function addRepairUpdate(
  token: string,
  downtimeEventId: number,
  payload: RepairUpdatePayload,
  signal?: AbortSignal,
) {
  return apiClient.post<EngineeringUpdateResponse>(
    `/api/v1/engineering/faults/${downtimeEventId}/updates`,
    payload,
    { token, signal },
  )
}

/** POST /api/v1/engineering/faults/{id}/close - the repair-update body
 * plus the required maintenance-preventability answer. */
export function closeFault(
  token: string,
  downtimeEventId: number,
  payload: CloseFaultPayload,
  signal?: AbortSignal,
) {
  return apiClient.post<EngineeringCloseResponse>(
    `/api/v1/engineering/faults/${downtimeEventId}/close`,
    payload,
    { token, signal },
  )
}

/** POST /api/v1/engineering/faults/{id}/handover */
export function handOverFault(
  token: string,
  downtimeEventId: number,
  payload: HandoverPayload,
  signal?: AbortSignal,
) {
  return apiClient.post<EngineeringHandoverResponse>(
    `/api/v1/engineering/faults/${downtimeEventId}/handover`,
    payload,
    { token, signal },
  )
}
