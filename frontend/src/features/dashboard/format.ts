/** Display-only formatting. Figures arrive already calculated and rounded
 * by the backend; nothing here recalculates a manufacturing figure. A
 * missing value is always shown as "—", never as 0. */

export const MISSING = '—'

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function fixed(value: number, min: number, max: number): string {
  return new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: min,
    maximumFractionDigits: max,
  }).format(value)
}

export function formatTonnes(value: number | null | undefined): string {
  return isNumber(value) ? `${fixed(value, 2, 2)} t` : MISSING
}

export function formatPallets(value: number | null | undefined): string {
  if (!isNumber(value)) return MISSING
  return `${fixed(value, 0, 1)} ${value === 1 ? 'pallet' : 'pallets'}`
}

export function formatPercent(value: number | null | undefined): string {
  return isNumber(value) ? `${fixed(value, 1, 1)}%` : MISSING
}

/** 0 → "0 min", 45.4 → "45 min", 125 → "2 h 05 min". */
export function formatMinutes(value: number | null | undefined): string {
  if (!isNumber(value)) return MISSING
  const total = Math.round(value)
  if (total < 60) return `${total} min`
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return `${hours} h ${String(minutes).padStart(2, '0')} min`
}

/** "Thu 25 Sep, 10:32" in UK time - the factory clock. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return MISSING
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return MISSING
  return date.toLocaleString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/London',
  })
}

/** "2026-09-21" (a calendar date, no time zone) → "21 Sep 2026". */
export function formatCalendarDate(isoDate: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate ?? '')
  if (!match) return MISSING
  const [, year, month, day] = match
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)))
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** The calendar date of a London-local ISO timestamp ("2026-09-21T06:00:00+01:00" → "2026-09-21"). */
export function localDatePart(isoLocal: string | null | undefined): string | null {
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(isoLocal ?? '')
  return match ? match[1] : null
}

/** Width of a comparison bar as a percentage of the largest value shown.
 * Visual scaling only - never displayed as a figure. */
export function barWidthPercent(value: number | null | undefined, largest: number): number {
  if (!isNumber(value) || !isNumber(largest) || largest <= 0 || value <= 0) return 0
  return Math.min(100, (value / largest) * 100)
}

/** Calendar arithmetic on "YYYY-MM-DD" dates (no time zone involved). */
export function addDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}

/** Today's calendar date on the factory clock (Europe/London). */
export function londonToday(now: Date = new Date()): string {
  // en-CA formats as YYYY-MM-DD.
  return now.toLocaleDateString('en-CA', { timeZone: 'Europe/London' })
}

const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-09-21" → "21 Sep" - a compact chart label. A fixed month table,
 * because ICU's en-GB short month for September varies ("Sep"/"Sept"). */
export function formatShortDate(isoDate: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate ?? '')
  if (!match) return MISSING
  const [, , month, day] = match
  return `${Number(day)} ${SHORT_MONTHS[Number(month) - 1]}`
}

/** "1.000" kg → "1 kg", 0.5 → "500 g". Display only. */
export function formatPackWeight(kg: number | null | undefined): string {
  if (!isNumber(kg)) return MISSING
  return kg >= 1 ? `${fixed(kg, 0, 3)} kg` : `${fixed(kg * 1000, 0, 0)} g`
}

export function formatCount(value: number | null | undefined): string {
  return isNumber(value) ? fixed(value, 0, 0) : MISSING
}
