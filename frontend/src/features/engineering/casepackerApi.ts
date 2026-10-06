import { apiClient } from '../../api/client'

export interface CasepackerRequest {
  id: number
  line_stoppage_id: number
  production_line: string
  details: string
  requested_by: string
  requested_at: string
  engineer: string | null
  accepted_at: string | null
  ready_at: string | null
  updates: { id: number; action: string; engineer: string; note: string; created_at: string }[]
}
export const getCasepackerStatus = (id: number, signal?: AbortSignal) =>
  apiClient.get<{ request: CasepackerRequest | null }>(`/api/v1/line-stoppages/${id}/casepacker`, { signal })
export const getCasepackerRequests = (token: string, signal?: AbortSignal) =>
  apiClient.get<{ items: CasepackerRequest[] }>('/api/v1/engineering/casepacker-requests', { token, signal })
export const actOnCasepacker = (token: string, id: number, action: 'accept' | 'update' | 'ready' | 'handover', note: string, idempotencyKey: string) =>
  apiClient.post(`/api/v1/engineering/casepacker-requests/${id}/actions`, { action, note }, { token, idempotencyKey })
