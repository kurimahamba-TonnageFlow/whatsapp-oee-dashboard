import { ActiveRuns } from '../features/management/ActiveRuns'
import { RequireManagementSession } from '../features/management/RequireManagementSession'

/** /management/active-runs - requires a Management session. Rendered
 * inside ManagementLayout (AppShell + shared session). */
export function ManagementActiveRunsPage() {
  return (
    <RequireManagementSession>
      <ActiveRuns />
    </RequireManagementSession>
  )
}
