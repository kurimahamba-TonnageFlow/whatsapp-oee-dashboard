/**
 * Display-only reference data. ENGINEERS matches
 * src/domain_constants.py's ENGINEERS tuple exactly (same order) -
 * the backend is still the source of truth for which name is actually
 * accepted (POST /api/v1/engineering/login validates server-side);
 * this list only drives the Engineer selection control.
 *
 * Max lengths match src/engineering_api.py's RepairUpdateRequest
 * Field(max_length=...) values exactly - enforced in the browser as a
 * courtesy, never as a substitute for the backend's own validation.
 */

import type { EngineeringFault } from './types'

export const ENGINEERS = ['Aaron', 'Yago', 'Steve', 'Dan', 'Kuri', 'Alfie'] as const

export const REPAIR_CLASSIFICATIONS = ['Mechanical', 'Machine Setting'] as const

/** Answers to "Could this fault have been prevented by planned
 * maintenance?", required at closure. */
export const MAINTENANCE_PREVENTABLE_OPTIONS = ['Yes', 'No', 'Unsure'] as const

export const MAX_TEXT_LENGTH = 2000
export const MAX_SHORT_FIELD_LENGTH = 200
export const MAX_REASON_LENGTH = 500
export const MAX_HANDOVER_NOTE_LENGTH = 500

export const FAULT_POLL_INTERVAL_MS = 30_000

// Keys match the live chk_engineering_status values exactly
// ('Not Started' / 'Ongoing' / 'Resolved') - the backend previously
// wrote the illegal value 'Investigating' here, which this map used to
// mirror; now corrected to match src/database.py's fix.
export const ENGINEERING_STATUS_LABELS: Record<string, string> = {
  'Not Started': 'Waiting for Engineer',
  Ongoing: 'Investigating',
  Resolved: 'Resolved',
}

/**
 * The exact, fixed `action` text src/engineering_api.py's /handover
 * endpoint writes for every genuine handover history record
 * (HANDOVER_ACTION_TEXT). This - not a NULL repair_classification, which
 * an ordinary unclassified Follow Up can also have - is the reliable
 * signal the UI uses to label a repair-update history entry as a
 * handover. No database column or migration is involved: this is a
 * plain string match against a field the API already returns.
 */
export const HANDOVER_ACTION_TEXT =
  'Job handed over; engineer unassigned and fault returned to Open Production Faults.'

export function engineeringStatusLabel(status: string): string {
  return ENGINEERING_STATUS_LABELS[status] ?? status
}

/**
 * Hand Over Job requires strictly more than "assigned to me": the
 * backend's guarded UPDATE (src/database.py: hand_over_engineering_fault)
 * only ever succeeds when the fault is still Ongoing, its
 * engineering_status is still 'Ongoing', it is assigned to this exact
 * engineer, AND it was genuinely accepted (accepted_at IS NOT NULL). A
 * legacy-assigned fault (engineer set outside the normal Accept flow,
 * accepted_at left NULL) would otherwise show a control that always
 * gets rejected with a 409. This mirrors that guard exactly so the
 * control never appears when the backend would refuse it - the backend
 * guard itself is unchanged and remains the actual authority.
 */
export function canHandOverFault(
  fault: Pick<EngineeringFault, 'engineer' | 'production_status' | 'engineering_status' | 'accepted_at'>,
  currentEngineer: string,
): boolean {
  return (
    fault.engineer === currentEngineer &&
    fault.production_status === 'Ongoing' &&
    fault.engineering_status === 'Ongoing' &&
    fault.accepted_at !== null
  )
}
