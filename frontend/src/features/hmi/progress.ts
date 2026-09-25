/**
 * Display helpers only. Every production figure (expected output,
 * actual output, gap, achievement, downtime minutes) is calculated by
 * the backend and read from GET /api/v1/runs/{id}/hmi-state - this file
 * must never recreate a manufacturing calculation.
 */
import type { StatusTone } from './components/StatusPill'

export function formatDuration(totalMinutes: number): string {
  const minutes = Math.max(Math.floor(totalMinutes), 0)
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `${hours}h ${remainder}m`
}

/** Mirrors the backend's line attention thresholds (see
 * docs/dashboard_integration.md): 95%+ on target, 85-95% at risk,
 * below 85% behind, no achievement figure yet = neutral. */
export function statusToneForAchievement(achievementPercent: number | null): StatusTone {
  if (achievementPercent === null) return 'blue'
  if (achievementPercent >= 95) return 'green'
  if (achievementPercent >= 85) return 'amber'
  return 'red'
}
