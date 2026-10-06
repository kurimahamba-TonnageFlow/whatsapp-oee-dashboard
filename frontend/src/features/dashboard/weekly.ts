import * as dashboardApi from './api'
import { addDays, localDatePart } from './format'
import type { WeeklyTargetProgress, WeeklyTargetsResponse } from './types'

/** How many production weeks the tonnage trend shows (this week included). */
export const TREND_WEEKS = 6

/**
 * GET /api/v1/dashboard/weekly-targets for this production week and the
 * previous TREND_WEEKS - 1, oldest first. Every figure is the backend's
 * own (same calculation as /overview); the browser only works out which
 * Mondays to ask for.
 */
export async function loadWeeklyTrend(token: string, signal: AbortSignal): Promise<WeeklyTargetsResponse[]> {
  const current = await dashboardApi.getWeeklyTargets(token, null, signal)
  const thisMonday = localDatePart(current.week.start_local)
  if (!thisMonday) return [current]

  const earlier = await Promise.all(
    Array.from({ length: TREND_WEEKS - 1 }, (_, index) =>
      dashboardApi.getWeeklyTargets(token, addDays(thisMonday, -7 * (TREND_WEEKS - 1 - index)), signal),
    ),
  )
  return [...earlier, current]
}

/** The site figures, or one line's, from a weekly-targets response. */
export function weekProgress(week: WeeklyTargetsResponse, line: string): WeeklyTargetProgress | null {
  if (!line) return week.site
  return week.lines.find((entry) => entry.production_line === line) ?? null
}
