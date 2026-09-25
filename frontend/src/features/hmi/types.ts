/**
 * HMI domain types. Every request/response type mirrors a confirmed
 * backend contract exactly (docs/hmi_integration.md, src/runs_api.py,
 * src/pulse_capture_api.py) - nothing here is guessed.
 *
 * Decimal values the operator enters (pallets, pack weight) are sent as
 * STRINGS so the exact decimal ("3.75") reaches the backend, which does
 * every calculation with Decimal precision. Numbers coming back are
 * already rounded by the backend for display.
 */

export interface StartRunPayload {
  production_line: string
  line_technician: string
  shift: string
  customer: string
  product: string
  pack_weight: string
  pack_weight_kg: number
  packs_per_case: number
  pack_type: string
  target_speed_ppm: number
  cases_per_pallet: number
  pallets_remaining: number
  previous_run_completed: number
  format?: string | null
}

export interface StartRunResponse {
  status: string
  message: string
  run_id: number
  production_line: string
  line_technician: string
  pallets_remaining: number
}

// ------------------------------------------------------------
// Active-run state (GET /api/v1/runs/{id}/hmi-state)
// ------------------------------------------------------------

export interface RunStateRun {
  run_id: number
  production_line: string
  line_technician: string
  shift: string
  customer: string
  product: string
  format: string | null
  pack_type: string
  pack_weight_kg: number
  packs_per_case: number
  cases_per_pallet: number
  target_speed_ppm: number
  status: string
  started_at: string
  finished_at: string | null
  starting_pallets_remaining: number
  pallets_remaining: number
  total_pallets_completed: number
  potential_overrun_pallets: number
}

export interface RunStateProgress {
  hourly_update_count: number
  pallets_recorded: number
  expected_packs: number
  actual_packs: number
  output_gap_packs: number
  expected_tonnes: number
  actual_tonnes: number
  production_achievement_percent: number | null
  /** Every planned stop merged, open ones counted to `generated_at`.
   * Overlapping stops are counted once, so this is the authority - it is
   * not necessarily completed + active. */
  planned_downtime_minutes: number
  /** Stops that have actually been ended. */
  planned_downtime_completed_minutes: number
  /** How long the one open stop has been running, from the server
   * clock. Null when nothing is stopped. */
  planned_downtime_active_minutes: number | null
  /** How long the open changeover has been running. Null when none. */
  changeover_active_minutes: number | null
  unplanned_downtime_minutes: number
  open_faults: number
  last_period_ended_at: string | null
  next_hourly_update_due_at: string
}

export interface PlannedDowntimeEvent {
  planned_downtime_id: number
  production_run_id: number
  production_line: string
  reason: string
  started_by: string
  started_at: string
  ended_by: string | null
  ended_at: string | null
  /** The final, stored duration. Null while the stop is still open. */
  duration_minutes: number | null
  is_active: boolean
  /** How long an open stop has been running, from the server clock.
   * Null once it has ended. */
  elapsed_minutes: number | null
}

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
  previous_customer: string | null
  previous_product: string | null
  previous_pack_weight_kg: number | null
  previous_format: string | null
  new_production_run_id: number | null
  new_customer: string
  new_product: string
  new_pack_weight_kg: number
  new_format: string
  note: string | null
}

export interface RunState {
  generated_at: string
  run: RunStateRun
  progress: RunStateProgress
  open_planned_downtime: PlannedDowntimeEvent | null
  open_changeover: Changeover | null
}

// ------------------------------------------------------------
// Cross-device line state (GET /api/v1/hmi/lines)
// ------------------------------------------------------------

export type StaleStatus = 'current' | 'stale' | 'unknown' | 'no_active_run'

/**
 * The authoritative answer to "is this line free?" - the same for every
 * tablet, because it comes from the database rather than from this
 * device's localStorage. Carries no Management-only figures.
 */
export interface HmiLineState {
  line_id: number
  production_line: string
  has_active_run: boolean
  run_id: number | null
  line_technician: string | null
  shift: string | null
  customer: string | null
  product: string | null
  started_at: string | null
  planned_downtime_active: boolean
  changeover_active: boolean
  engineering_fault_open: boolean
  open_fault_count: number
  last_activity_at: string | null
  stale_status: StaleStatus
  stale_reason: string | null
  minutes_since_last_hourly_update: number | null
}

export interface HmiLineStateResponse {
  generated_at: string
  stale_after_minutes: number
  lines: HmiLineState[]
}

// ------------------------------------------------------------
// Writes
// ------------------------------------------------------------

export interface HourlyUpdatePayload {
  line_technician: string
  /** Decimal string, e.g. "3.75". "0" is valid. */
  pallets_produced: string
  other_loss_reason?: string | null
}

export interface HourlyUpdateResponse {
  status: string
  hourly_update_id: number
  production_run_id: number
  production_line: string
  shift: string
  period_started_at: string
  period_ended_at: string
  period_minutes: number
  pallets_produced: number
  expected_packs: number
  expected_pallets: number
  expected_tonnes: number
  actual_packs: number
  actual_tonnes: number
  output_gap_packs: number
  production_achievement_percent: number | null
  planned_downtime_minutes: number
  pallets_remaining: number
  total_pallets_completed: number
  potential_overrun_pallets: number
}

export interface PlannedDowntimeStartPayload {
  reason: string
  started_by: string
}

export interface PlannedDowntimeEndPayload {
  ended_by: string
}

export type PlannedDowntimeResponse = PlannedDowntimeEvent & { status: string }

export interface FaultReportPayload {
  reported_by: string
  machine: string
  reason: string
  machine_id?: number | null
  button_id?: number | null
  note?: string | null
}

export interface FaultReportResponse {
  status: string
  downtime_event_id: number
  production_run_id: number
  production_line: string
  fault_id: number
  machine: string
  reason: string
  reported_by: string
  production_status: string
  engineering_status: string
  opened_at: string
}

export interface ChangeoverStartPayload {
  line_technician: string
  new_customer: string
  new_product: string
  /** Decimal string, e.g. "4". */
  new_pack_weight_kg: string
  new_format: string
  note?: string | null
}

export interface ChangeoverCompletePayload {
  completed_by: string
  first_acceptable_packs_confirmed: true
  note?: string | null
}

export interface ChangeoverPairResponse {
  status: string
  changeover: Changeover
  planned_downtime: PlannedDowntimeEvent
}

export interface CompletionPayload {
  line_technician: string
  production_since_last_update: boolean
  /** Decimal string when production_since_last_update is true. */
  final_pallets_produced?: string | null
  count_unavailable?: boolean
  xray_pack_count?: number | null
  unavailable_reason?: string | null
}

export interface CompletionPreviewResponse {
  production_run_id: number
  production_line: string
  total_pallets_recorded: number
  final_pallets_produced: number
  palletised_pallets: number
  palletised_packs: number
  count_available: boolean
  xray_pack_count: number | null
  post_xray_pack_difference: number | null
  estimated_post_xray_waste_percent: number | null
  waste_status: 'estimated' | 'unavailable' | 'data_quality_warning' | 'no_output'
  waste_unavailable_reason: string | null
  data_quality_warning: string | null
  calculation_status: 'estimated' | 'unavailable'
  method: string
  /** False when the recorded figures contradict each other (more packs
   * palletised than the X-ray counted). The write path refuses such a
   * completion with 409, so the HMI blocks Confirm and sends the
   * operator back to correct the input. */
  can_complete: boolean
  blocking_reason: string | null
  saved: false
}

export interface XrayCaptureResponse {
  xray_capture_id: number
  capture_point: string
  production_run_id: number
  production_line: string
  shift: string
  captured_at: string
  final_hourly_update_id: number | null
  final_pallets_produced: number | null
  total_pallets_recorded: number
  count_available: boolean
  xray_pack_count: number | null
  unavailable_reason: string | null
  palletised_pallets: number
  palletised_packs: number
  post_xray_pack_difference: number | null
  estimated_post_xray_waste_percent: number | null
  waste_status: string
  waste_unavailable_reason: string | null
  data_quality_warning: string | null
  calculation_status: string
  method: string
}

export interface CompleteRunResponse {
  status: string
  message: string
  run_id: number
  production_line: string
  run_status: string
  xray: XrayCaptureResponse
}

// ------------------------------------------------------------
// Local form + storage shapes
// ------------------------------------------------------------

/** What the operator entered on the Start Run form, in UI-friendly
 * (camelCase, already-parsed-number) shape. Converted to
 * StartRunPayload only at submit time. */
export interface StartRunFormValues {
  productionLine: string
  lineTechnician: string
  shift: string
  customer: string
  product: string
  packWeightLabel: string
  packWeightKg: string
  packsPerCase: string
  packType: string
  targetSpeedPpm: string
  casesPerPallet: string
  palletsRemaining: string
  previousRunCompleted: string
}

export const EMPTY_START_RUN_FORM: StartRunFormValues = {
  productionLine: '',
  lineTechnician: '',
  shift: '',
  customer: '',
  product: '',
  packWeightLabel: '',
  packWeightKg: '',
  packsPerCase: '',
  packType: '',
  targetSpeedPpm: '',
  casesPerPallet: '',
  palletsRemaining: '',
  previousRunCompleted: '0',
}

/** Start Changeover form values, before conversion to
 * ChangeoverStartPayload (new_pack_weight_kg stays a string). */
export interface ChangeoverFormValues {
  newCustomer: string
  newProduct: string
  newPackWeightKg: string
  newFormat: string
  note: string
}

export const EMPTY_CHANGEOVER_FORM: ChangeoverFormValues = {
  newCustomer: '',
  newProduct: '',
  newPackWeightKg: '',
  newFormat: '',
  note: '',
}

/** Complete Run form values. productionSinceLastUpdate starts empty so
 * the operator has to answer it deliberately - a final production
 * figure must never be assumed. */
export interface CompleteRunFormValues {
  productionSinceLastUpdate: 'yes' | 'no' | ''
  finalPallets: string
  countUnavailable: boolean
  xrayPackCount: string
  unavailableReason: string
}

export const EMPTY_COMPLETE_RUN_FORM: CompleteRunFormValues = {
  productionSinceLastUpdate: '',
  finalPallets: '',
  countUnavailable: false,
  xrayPackCount: '',
  unavailableReason: '',
}

/**
 * The only thing this tablet remembers about the run in progress: which
 * run it is. Everything shown on screen is re-read from the backend
 * (GET /api/v1/runs/{id}/hmi-state), so totals, planned downtime and
 * changeovers always come from the database, never from local state.
 */
export interface StoredActiveRun {
  runId: number
  productionLine: string
}
