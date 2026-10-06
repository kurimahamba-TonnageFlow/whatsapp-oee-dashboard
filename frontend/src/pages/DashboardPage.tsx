import { ProductionDashboard } from '../features/dashboard/ProductionDashboard'

/** /dashboard - Production. Rendered inside DashboardLayout, behind
 * RequireManagementSession (every dashboard endpoint needs a session). */
export function DashboardPage() {
  return <ProductionDashboard />
}
