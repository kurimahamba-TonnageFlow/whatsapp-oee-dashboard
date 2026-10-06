export interface DashboardNavItem {
  to: string
  label: string
  /** Decorative glyph shown in the side rail. */
  icon: string
  /** Opens in a new tab, so the Management session in this tab carries on. */
  newTab?: boolean
}

/** The four management dashboard pages, in reading order. */
export const DASHBOARD_PAGES: ReadonlyArray<DashboardNavItem> = [
  { to: '/dashboard', label: 'Production', icon: '▥' },
  { to: '/dashboard/engineering', label: 'Engineering', icon: '⚒' },
  { to: '/dashboard/qa', label: 'QA', icon: '◇' },
  { to: '/dashboard/operational-intelligence', label: 'Operational Intelligence', icon: '◎' },
]

/** The existing Pulse areas, still one click away. Leaving the
 * Management area in this tab ends the Management session (by design -
 * see ManagementSessionProvider), so the Engineering workspace, which
 * has its own sign-in, opens in a new tab. */
export const OTHER_AREAS: ReadonlyArray<DashboardNavItem> = [
  { to: '/management', label: 'Management', icon: '☰' },
  { to: '/management/performance', label: 'Performance', icon: '↗' },
  { to: '/engineering', label: 'Engineering workspace', icon: '⚙', newTab: true },
  { to: '/hmi', label: 'HMI', icon: '▣' },
]
