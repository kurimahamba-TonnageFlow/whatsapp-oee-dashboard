/** LIVE backend call - GET only, Management session required. */
import { apiClient } from '../../api/client'
import type { PerformanceFilters, TechnicianPerformanceResponse } from './types'

export function getTechnicianPerformance(
  token: string,
  filters: PerformanceFilters,
  signal?: AbortSignal,
) {
  const search = new URLSearchParams()
  search.set('period', filters.period)
  if (filters.period === 'custom') {
    search.set('date_from', filters.date_from)
    search.set('date_to', filters.date_to)
  }
  for (const key of ['production_line', 'shift', 'technician', 'product', 'customer'] as const) {
    if (filters[key]) search.set(key, filters[key])
  }
  return apiClient.get<TechnicianPerformanceResponse>(
    `/api/v1/management/technician-performance?${search.toString()}`,
    { token, signal },
  )
}
