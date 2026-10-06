import type { AttentionStatus, DashboardWindow } from './types'

/** The four factory-time windows /overview supports (Europe/London). */
export const PERIOD_OPTIONS: ReadonlyArray<{ value: DashboardWindow; label: string }> = [
  { value: 'current_shift', label: 'Current shift' },
  { value: 'factory_day', label: 'Today (from 06:00)' },
  { value: 'production_week', label: 'This week (from Monday 06:00)' },
  { value: 'rolling_24h', label: 'Last 24 hours' },
]

export const DEFAULT_PERIOD: DashboardWindow = 'factory_day'

/** The approved production lines, in factory order. */
export const DASHBOARD_LINES = ['Rovema', 'GIC', 'Guill'] as const

export const RUNS_PAGE_SIZE = 25

/** Plain-language meaning of the backend's line attention status
 * (docs/dashboard_integration.md "Line attention status"). */
export const ATTENTION: Record<AttentionStatus, { label: string; order: number }> = {
  red: { label: 'Needs attention', order: 0 },
  amber: { label: 'Behind target', order: 1 },
  green: { label: 'On target', order: 2 },
  grey: { label: 'No production data', order: 3 },
}
