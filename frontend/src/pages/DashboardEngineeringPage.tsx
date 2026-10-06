import { EngineeringDashboard } from '../features/dashboard/engineering/EngineeringDashboard'

/** /dashboard/engineering - read-only fault reporting. Fault handling
 * itself stays in the Engineering workspace at /engineering. */
export function DashboardEngineeringPage() {
  return <EngineeringDashboard />
}
