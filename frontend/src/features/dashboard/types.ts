import type { OperatingReport } from '../shared/OperatingContext'
/** Confirmed contracts from src/dashboard_api.py, src/dashboard_reports.py
 * and docs/dashboard_integration.md. Every figure is calculated by the
 * backend (src/pulse_calculations.py); the dashboard only formats it. */

export type DashboardWindow = 'current_shift' | 'factory_day' | 'production_week' | 'rolling_24h'

export type AttentionStatus = 'red' | 'amber' | 'green' | 'grey'

export interface WindowInfo {
  kind: DashboardWindow
  label: string
  timezone: string
  start: string
  end: string
  start_local: string
  end_local: string
}

export interface OutputFigures {
  expected_packs: number
  expected_pallets: number
  expected_tonnes: number
  actual_packs: number
  actual_pallets: number
  actual_tonnes: number
  output_gap_packs: number
  output_gap_pallets: number
  output_gap_tonnes: number
  /** actual / expected tonnes x 100 - NOT OEE. null when nothing was expected. */
  production_achievement_percent: number | null
  hourly_update_count: number
}

export interface EstimatedLoss {
  estimated_lost_packs: number
  estimated_lost_pallets: number
  estimated_lost_tonnes: number
}

export interface DowntimeLoss extends EstimatedLoss {
  minutes: number
}

export interface GapAttribution {
  reconciliation?: {
    signed_variance_packs: number
    shortfall_packs: number
    overproduction_packs: number
    excess_modelled_packs: number
    operating_context?: OperatingReport[]
    raw_planned_packs: number
    raw_unplanned_packs: number
    covered_periods: number
    total_periods: number
    coverage_complete: boolean
    reported_explanations?: string[]
    limitations: string[]
  }
  calculation_status: string
  method: string
  measured_output_gap: EstimatedLoss
  planned_downtime: DowntimeLoss
  unplanned_downtime: DowntimeLoss
  other_or_speed_loss: EstimatedLoss
  unexplained_gap: EstimatedLoss
  /** Ranked by estimated tonnes lost; each sums to the capped totals. */
  by_machine?: RankedLoss[]
  by_planned_reason?: RankedLoss[]
}

export interface ActiveRun {
  run_id: number
  line_technician: string
  shift: string
  customer: string
  product: string
  format: string | null
  started_at: string
  pallets_remaining: number | null
  total_pallets_completed: number | null
}

export interface LineSummary {
  reported_palletised_output?: OutputFigures
  production_line: string
  attention_status: AttentionStatus
  attention_explanation: string
  open_faults: number
  active_run: ActiveRun | null
  output: OutputFigures
  downtime_minutes: { planned: number; unplanned: number }
  freshness: {
    latest_activity_at: string | null
    last_hourly_update_at: string | null
    stale_status: string
    stale_reason?: string | null
  }
}

export interface DataQuality {
  legacy_records_excluded: boolean
  legacy_record_count: number
  message: string | null
}

export interface DashboardOverview {
  reported_palletised_output?: OutputFigures
  generated_at: string
  window: WindowInfo
  freshness: {
    latest_activity_at: string | null
    last_hourly_update_at: string | null
    stale_status: string
    stale_lines: string[]
    stale_after_minutes: number
  }
  output: OutputFigures
  gap_attribution: GapAttribution
  /** Stops between product runs, charged to the line only. */
  line_stops?: LineStops
  /** Present on live responses; not shown on the dashboard pages. */
  estimated_oee?: EstimatedOee
  open_faults: number
  lines: LineSummary[]
  data_quality: DataQuality
}

export interface DashboardRun {
  run_id: number
  production_line: string
  line_technician: string
  shift: string
  customer: string
  product: string
  pack_type: string
  status: string
  started_at: string
  finished_at: string | null
  total_pallets_completed: number
  /** 0 when the run has no hourly updates - its output fields are then null. */
  hourly_update_count: number
  expected_tonnes: number | null
  actual_tonnes: number | null
  output_gap_tonnes: number | null
}

export interface DashboardRunsResponse {
  items: DashboardRun[]
  total: number
  page: number
  page_size: number
}

export interface DashboardFilterOptions {
  production_lines: string[]
  shifts: string[]
  products: string[]
  customers: string[]
  technicians: string[]
  engineers?: string[]
  machines?: string[]
  fault_statuses?: string[]
}

export interface RunFilters {
  technician: string
  shift: string
  customer: string
  product: string
}

/** Estimated OEE block on /overview (site and per line). Deliberately
 * not shown on the dashboard pages yet - see docs/dashboard_integration.md. */
export interface EstimatedOee {
  availability_percent: number | null
  performance_percent: number | null
  estimated_quality_percent: number | null
  estimated_oee_percent: number | null
  calculation_status: 'estimated' | 'partial' | 'unavailable'
  calculation_method: string
  unavailable_reason: string | null
}

/** One ranked entry in gap_attribution.by_machine / by_planned_reason. */
export interface RankedLoss extends DowntimeLoss {
  production_line?: string
  machine?: string
  reason?: string
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/weekly-targets (build_weekly_targets)
// ----------------------------------------------------------

export type TargetStatus = 'green' | 'red' | 'grey'

export interface WeeklyTargetProgress {
  scope: 'site' | 'line'
  production_line: string | null
  target_tonnes: number | null
  actual_tonnes: number | null
  tonnes_remaining: number | null
  percent_complete: number | null
  expected_tonnes_by_now: number | null
  week_elapsed_percent: number | null
  target_status: TargetStatus
  status_reason: string | null
}

export interface WeeklyTargetsResponse {
  generated_at: string
  week: WindowInfo
  latest_activity_at: string | null
  pace_method: string
  site: WeeklyTargetProgress
  lines: WeeklyTargetProgress[]
  data_quality: DataQuality
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/machines (build_machine_summary)
// ----------------------------------------------------------

export interface MachineSummary {
  production_line: string
  machine: string
  fault_count: number
  open_faults: number
  downtime_minutes_in_window: number
  maintenance_preventable: { Yes: number; No: number; Unsure: number; not_recorded: number }
  estimated_lost_tonnes: number
  estimated_lost_pallets: number
  estimated_lost_packs: number
}

export interface MachinesResponse {
  generated_at: string
  window: WindowInfo
  ranking_basis: string
  method: string
  machines: MachineSummary[]
  data_quality: DataQuality
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/engineering-classification
// ----------------------------------------------------------

export interface FaultBucket {
  fault_count: number
  downtime_minutes_in_window: number
}

export interface EngineeringClassificationResponse {
  generated_at: string
  window: WindowInfo
  by_repair_classification: Record<
    'machine_setup_or_setting' | 'physical_component_failure' | 'not_classified',
    FaultBucket
  >
  by_maintenance_preventable: Record<'yes' | 'no' | 'unsure' | 'not_recorded', FaultBucket>
  by_status: Record<'open' | 'closed', FaultBucket>
  data_quality: DataQuality
  notes: string[]
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/faults (get_dashboard_faults)
// ----------------------------------------------------------

export interface DashboardFault {
  downtime_event_id: number
  production_run_id: number
  production_line: string
  fault_id: number
  machine: string
  reason: string
  reported_by: string
  engineer_called: boolean
  /** 'Ongoing' | 'Resolved' */
  production_status: string
  engineering_status: string
  engineer: string | null
  retrospective: boolean
  opened_at: string
  resolved_at: string | null
  duration_minutes: number
  /** true: still open, so the duration runs to "now" on the server. */
  duration_is_active: boolean
}

export interface DashboardFaultsResponse {
  items: DashboardFault[]
  total: number
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/changeovers (build_changeover_report)
// ----------------------------------------------------------

export type ChangeoverGroupBy = 'line' | 'week' | 'day' | 'month' | 'duration'

export interface Changeover {
  changeover_id: number
  production_line: string
  line_technician: string
  shift: string
  status: 'Open' | 'Completed'
  started_at: string
  completed_at: string | null
  completed_by: string | null
  duration_minutes: number | null
  /** End Run -> Changeover only: physical work, then new-run setup. */
  physical_minutes?: number | null
  setup_minutes?: number | null
  previous_customer: string | null
  previous_product: string | null
  previous_pack_weight_kg: number | null
  previous_format: string | null
  new_customer: string | null
  new_product: string | null
  new_pack_weight_kg: number | null
  new_format: string | null
  note: string | null
}

export interface ChangeoverGroup {
  key: string | number | null
  changeover_count: number
  completed_count: number
  open_count: number
  total_duration_minutes: number
  average_duration_minutes: number | null
  longest_duration_minutes: number | null
}

export interface ChangeoversResponse {
  generated_at: string
  definition: string
  group_by: ChangeoverGroupBy | null
  groups: ChangeoverGroup[] | null
  changeovers: Changeover[]
}

export interface ChangeoverFilters {
  date_from: string
  date_to: string
  production_line: string
  customer: string
  product: string
  status: '' | 'Open' | 'Completed'
}

// ----------------------------------------------------------
// GET /api/v1/dashboard/hourly (src/hourly_reports.py)
// ----------------------------------------------------------

export type HourStatus = 'reported' | 'no_reading' | 'in_progress' | 'stopped' | 'idle' | 'not_scheduled'

export interface StopReason {
  /** not_scheduled: shown beside the reasons, never in the stopped minutes. */
  kind: 'planned' | 'unplanned' | 'not_scheduled'
  reason: string
  minutes: number
}

interface HourStops {
  stopped_minutes: number
  planned_minutes: number
  unplanned_minutes: number
  stop_reasons: StopReason[]
}

export interface HourRunResult extends HourStops {
  run_id: number
  product: string
  customer: string
  line_technician: string
  status: HourStatus
  applicable_start: string
  applicable_end: string
  applicable_minutes: number
  is_partial_hour: boolean
  target_speeds: { from: string; to: string; speed_ppm: number }[]
  actual_speed_ppm: number | null
  target_packs: number
  actual_packs: number | null
  output_vs_target_percent: number | null
  is_low_output: boolean
}

export interface HourLineResult extends HourStops {
  status: HourStatus
  target_packs: number
  actual_packs: number | null
  output_vs_target_percent: number | null
  is_low_output: boolean
  covered_minutes: number
  unaccounted_minutes: number
  /** In no target and in neither planned nor unplanned downtime. */
  not_scheduled_minutes?: number
  stoppage_reference_missing: boolean
}

export interface HourSlot {
  hour_start: string
  hour_end: string
  hour_label: string
  is_complete: boolean
  line: HourLineResult
  runs: HourRunResult[]
}

export interface HourlyLine {
  production_line: string
  latest_completed_hour: HourSlot | null
  hours: HourSlot[]
}

export interface HourlyReport {
  generated_at: string
  window: WindowInfo
  measure: string
  method: string
  low_output_percent: number
  denominators: { run: string; line: string }
  lines: HourlyLine[]
}

export interface LineStopReason {
  production_line: string
  downtime_type: 'planned' | 'unplanned' | 'not_scheduled'
  reason: string
  minutes: number
  /** At the previous run's target speed and pack weight; null if unknown. */
  estimated_lost_tonnes: number | null
}

export interface LineStops {
  planned_minutes: number
  unplanned_minutes: number
  not_scheduled_minutes?: number
  by_reason: LineStopReason[]
  note: string
}

export type LineStopKind = 'handover' | 'changeover' | 'other' | 'restart_delay' | 'not_scheduled'

export interface LineStopReclassification {
  reclassification_id: number
  previous_kind: LineStopKind
  previous_reason: string | null
  new_kind: LineStopKind
  new_reason: string | null
  changed_by: string
  changed_at: string
  note: string
}

export interface LineStopLogEntry {
  stoppage_id: number
  production_line: string
  kind: LineStopKind
  downtime_type: 'planned' | 'unplanned' | 'not_scheduled'
  reason: string | null
  started_by: string
  started_at: string
  ended_by: string | null
  ended_at: string | null
  is_open: boolean
  minutes: number
  follows_stoppage_id: number | null
  /** Exactly what the backend will accept for this stop. */
  allowed_reclassifications: LineStopKind[]
  reclassifications: LineStopReclassification[]
}

export interface LineStopLog {
  generated_at: string
  stops: LineStopLogEntry[]
}
