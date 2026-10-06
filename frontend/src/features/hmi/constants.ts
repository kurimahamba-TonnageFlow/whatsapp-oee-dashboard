import catalogue from '../../../../src/production_catalogue.json'
/**
 * Static reference data for the Start Run form. Matches the backend's
 * own confirmed configuration exactly:
 *   - PRODUCTION_LINES: src/main.py line_technicians_by_line keys
 *   - LINE_TECHNICIANS: src/main.py _all_line_technicians (no line
 *     restriction - every technician is valid on every line, matching
 *     docs/hmi_integration.md)
 *   - SHIFTS: docs/hmi_integration.md / this stage's instructions
 * PRODUCTS and CUSTOMERS are not backend-validated (production_line and
 * line_technician are the only fields the API restricts to a known
 * list - see docs/hmi_integration.md), the displayed choices come from the shared production catalogue.
 */

/** How often Home re-reads the authoritative line state. 20s is short
 * enough that a tablet notices another device starting a run before an
 * operator has finished walking to the line, and light enough for a
 * factory tablet on site Wi-Fi. Polling stops while the tab is hidden. */
export const LINE_STATE_POLL_INTERVAL_MS = 20_000

export const PRODUCTION_LINES = ['Rovema', 'GIC', 'Guill'] as const

export const LINE_TECHNICIANS = [
  'Marina',
  'Mariusz',
  'Liam',
  'Ben',
  'Tomasz',
  'Sumit',
  'Gurpreet',
  'Baljeet',
  'Pali',
  'Diego',
  'Seb',
  'Bupreet',
] as const

export interface ShiftDefinition {
  name: 'Days' | 'Afternoons' | 'Nights'
  label: string
  startHour: number
  endHour: number
}

export const SHIFTS = catalogue.shifts as ShiftDefinition[]

export const PRODUCTS = catalogue.products

/** Current catalogue; historical aliases are preserved by backend filters. */
export const CUSTOMERS = catalogue.customers

/** Initial planned-downtime buttons, used until/unless
 * GET /api/v1/hmi/config supplies configured planned_downtime buttons
 * for the selected line (see screens/PlannedDowntimeScreen.tsx). */
export const DEFAULT_PLANNED_DOWNTIME_REASONS = [
  'Label Change',
  'Film Change',
  'CCP Check',
  'Changeover',
] as const
