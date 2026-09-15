/**
 * Types here mirror confirmed backend response shapes only (see
 * docs/hmi_integration.md, docs/management_integration.md,
 * docs/dashboard_integration.md, and src/whatsapp_webhook.py for
 * /health). Nothing is guessed - fields not documented or not present
 * in a backend response model are not represented here. More types
 * will be added as each feature area is actually built.
 */

/** GET /health (src/whatsapp_webhook.py) */
export interface HealthResponse {
  status: string
  service: string
}

/** GET /api/v1/hmi/config (src/hmi_config_api.py) */
export interface HmiConfigButton {
  id: number
  name: string
  event_type: 'planned_downtime' | 'unplanned_fault'
  ownership: 'Production' | 'Engineering'
  fault_category: string | null
}

export interface HmiConfigMachine {
  id: number
  name: string
  buttons: HmiConfigButton[]
}

export interface HmiConfigLine {
  id: number
  name: string
  machines: HmiConfigMachine[]
}

export interface HmiConfigResponse {
  lines: HmiConfigLine[]
}
