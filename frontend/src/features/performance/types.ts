/** GET /api/v1/management/technician-performance (src/management_api.py,
 * database.get_technician_performance, docs/management_integration.md). */

export type PerformancePeriod =
  | 'today'
  | 'yesterday'
  | 'current_week'
  | 'previous_week'
  | 'current_month'
  | 'previous_month'
  | 'current_quarter'
  | 'previous_quarter'
  | 'current_year'
  | 'custom'

export interface TechnicianResult {
  coverage_complete?: boolean
  limitations?: string[]
  reported_tonnes?: number
  line_technician: string
  completed_runs: number
  expected_pallets: number
  actual_pallets: number
  expected_tonnes: number
  actual_tonnes: number
  output_gap_pallets: number
  output_gap_tonnes: number
  /** null (never 0) when there was no expected output to compare against. */
  target_achievement_percent: number | null
  data_completion_rate_percent: number | null
  /** "On target" / "At risk" / "Needs review" / "Insufficient data". */
  label: string
  lines: string[]
}

export interface TechnicianPerformanceResponse {
  period: string
  date_from: string | null
  date_to: string | null
  minimum_sample_size: number
  /** Already ordered by the backend (best achievement first, no-data last). */
  ranked: TechnicianResult[]
  insufficient_data: TechnicianResult[]
}

export interface PerformanceFilters {
  period: PerformancePeriod
  date_from: string
  date_to: string
  production_line: string
  shift: string
  technician: string
  product: string
  customer: string
}
