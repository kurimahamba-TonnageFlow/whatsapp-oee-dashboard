import { SHIFTS, type ShiftDefinition } from './constants'

/**
 * Resolves the current shift from the clock. Uses the browser's local
 * time - the HMI runs on tablets physically on the UK factory floor,
 * so local time is UK time; no timezone-conversion library is used.
 */
export function resolveCurrentShift(date: Date = new Date()): ShiftDefinition {
  const hour = date.getHours()

  const shift = SHIFTS.find((candidate) => {
    if (candidate.startHour < candidate.endHour) {
      return hour >= candidate.startHour && hour < candidate.endHour
    }
    // Wraps midnight (Nights: 22:00-06:00)
    return hour >= candidate.startHour || hour < candidate.endHour
  })

  // SHIFTS covers all 24 hours, so this is unreachable, but keeps the
  // return type non-optional without a non-null assertion.
  return shift ?? SHIFTS[0]
}

export function formatUkDateTime(date: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
