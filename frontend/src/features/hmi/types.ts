/**
 * HMI domain types. StartRunPayload/StartRunResponse/CompleteRunResponse
 * mirror the confirmed backend contract exactly (docs/hmi_integration.md,
 * src/runs_api.py) - nothing here is guessed.
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
}

export interface StartRunResponse {
  status: string
  message: string
  run_id: number
  production_line: string
  line_technician: string
  pallets_remaining: number
}

export interface CompleteRunResponse {
  status: string
  message: string
  run_id: number
  production_line: string
  run_status: string
}

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

/**
 * A run this device has started and confirmed via the live API.
 * Persisted in this browser's localStorage only (see
 * activeRunStorage.ts) so a page refresh restores the Active Run
 * screen instead of losing track of it or bouncing back to Home.
 * Not a fixture - every field came from a real, API-confirmed
 * Start Run submission.
 */
export interface ActiveRunRecord {
  runId: number
  startedAtIso: string
  form: StartRunFormValues
  totalPalletsCompleted: number
  plannedDowntimeMinutes: number
  unplannedDowntimeMinutes: number
}
