import { RequireManagementSession } from '../features/management/RequireManagementSession'
import { TechnicianPerformance } from '../features/performance/TechnicianPerformance'

/** /management/performance - requires a Management session. Rendered
 * inside ManagementLayout (AppShell + shared session). */
export function ManagementPerformancePage() {
  return (
    <RequireManagementSession>
      <TechnicianPerformance />
    </RequireManagementSession>
  )
}
