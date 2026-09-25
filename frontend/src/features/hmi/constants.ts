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
 * list - see docs/hmi_integration.md), so these are the frontend's own
 * reference lists.
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

export const SHIFTS: ShiftDefinition[] = [
  { name: 'Days', label: 'Days (06:00–14:00)', startHour: 6, endHour: 14 },
  { name: 'Afternoons', label: 'Afternoons (14:00–22:00)', startHour: 14, endHour: 22 },
  { name: 'Nights', label: 'Nights (22:00–06:00)', startHour: 22, endHour: 6 },
]

export const PRODUCTS = [
  'White Basmati',
  'Brown Basmati',
  'White Long Grain',
  'Brown Long Grain',
  'Arborio',
  'Pudding',
  'Risotto',
  'White LG Easy Cook',
  'Brown LG Easy Cook',
  'Jasmine',
  'Thai Sticky',
  'Thai Pathum Thani',
  'Sushi',
  'Thai Hom Mali',
] as const

/**
 * Confirmed customers: Asda and Tesco appear in this project's own
 * README worked examples; Morissons was observed in live production
 * data during the Stage 2 migration verification (spelling preserved
 * exactly as seen live, not "corrected"). Waitrose added per explicit
 * instruction.
 */
export const CUSTOMERS = ['Asda', 'Tesco', 'Morissons', 'Waitrose'] as const

/** Initial planned-downtime buttons, used until/unless
 * GET /api/v1/hmi/config supplies configured planned_downtime buttons
 * for the selected line (see screens/PlannedDowntimeScreen.tsx). */
export const DEFAULT_PLANNED_DOWNTIME_REASONS = [
  'Label Change',
  'Film Change',
  'CCP Check',
  'Changeover',
] as const
