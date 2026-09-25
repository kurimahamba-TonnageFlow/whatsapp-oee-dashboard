/**
 * Types here mirror confirmed backend response/request shapes only
 * (docs/engineering_integration.md, src/engineering_api.py). Nothing
 * here is guessed or invented - fields not present in the documented
 * contract are not represented here.
 */

export type RepairClassification = 'Mechanical' | 'Machine Setting'

/** POST /api/v1/engineering/login request body. */
export interface EngineeringLoginPayload {
  pin: string
  engineer_name: string
}

/** POST /api/v1/engineering/login response (200). */
export interface EngineeringLoginResponse {
  status: string
  token: string
  engineer_name: string
  expires_at: string
}

/** One entry in EngineeringFault.repair_updates. */
export interface EngineeringFaultRepairUpdate {
  id: number
  engineer: string | null
  update_type: string
  repair_classification: RepairClassification | null
  finding: string | null
  action: string | null
  notes: string | null
  setting_name: string | null
  previous_value: string | null
  new_value: string | null
  reason_for_change: string | null
  affected_products_or_formats: string | null
  engineering_status: string
  created_at: string
}

/** GET /api/v1/engineering/faults - one item. */
export interface EngineeringFault {
  downtime_event_id: number
  production_run_id: number
  production_line: string
  fault_id: number
  machine: string
  reason: string
  reported_by: string
  engineer: string | null
  production_status: string
  engineering_status: string
  opened_at: string
  accepted_at: string | null
  resolved_at: string | null
  duration_minutes: number
  duration_is_active: boolean
  repair_updates: EngineeringFaultRepairUpdate[]
}

/** GET /api/v1/engineering/faults response (200). */
export interface EngineeringFaultsResponse {
  items: EngineeringFault[]
  total: number
}

/** POST /api/v1/engineering/faults/{id}/accept response (200). */
export interface EngineeringAcceptResponse {
  status: string
  downtime_event_id: number
  engineer: string
  engineering_status: string
  accepted_at: string | null
}

/** "Could this fault have been prevented by planned maintenance?" -
 * required when closing a fault (src/engineering_api.py:
 * CloseFaultRequest). Never inferred from notes. */
export type MaintenancePreventable = 'Yes' | 'No' | 'Unsure'

/**
 * POST /api/v1/engineering/faults/{id}/updates request body
 * (src/engineering_api.py: RepairUpdateRequest). Closing a fault uses
 * the same shape plus maintenance_preventable - see CloseFaultPayload.
 */
export interface RepairUpdatePayload {
  classification: RepairClassification
  finding: string
  action: string
  notes?: string | null
  setting_name?: string | null
  previous_value?: string | null
  new_value?: string | null
  reason_for_change?: string | null
  affected_products_or_formats?: string | null
}

/** POST /api/v1/engineering/faults/{id}/close request body. */
export interface CloseFaultPayload extends RepairUpdatePayload {
  maintenance_preventable: MaintenancePreventable
}

/** POST /api/v1/engineering/faults/{id}/updates response (200). */
export interface EngineeringUpdateResponse {
  status: string
  downtime_event_id: number
  engineering_update_id: number
  created_at: string
}

/** POST /api/v1/engineering/faults/{id}/close response (200). */
export interface EngineeringCloseResponse {
  status: string
  downtime_event_id: number
  engineer: string | null
  engineering_status: string
  production_status: string
  resolved_at: string | null
  /** Echoed back from the stored fault. Null only for a fault closed
   * before this answer was required. */
  maintenance_preventable: MaintenancePreventable | null
}

/** POST /api/v1/engineering/faults/{id}/handover request body. */
export interface HandoverPayload {
  note: string
}

/** POST /api/v1/engineering/faults/{id}/handover response (200). */
export interface EngineeringHandoverResponse {
  status: string
  downtime_event_id: number
  engineer: string | null
  engineering_status: string
  production_status: string
  accepted_at: string | null
}
