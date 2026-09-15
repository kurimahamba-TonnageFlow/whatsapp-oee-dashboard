import { Navigate, Route, Routes } from 'react-router-dom'
import { HmiPage } from '../pages/HmiPage'
import { EngineeringPage } from '../pages/EngineeringPage'
import { ManagementPage } from '../pages/ManagementPage'
import { ManagementPerformancePage } from '../pages/ManagementPerformancePage'
import { DashboardPage } from '../pages/DashboardPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/hmi" replace />} />
      <Route path="/hmi" element={<HmiPage />} />
      <Route path="/engineering" element={<EngineeringPage />} />
      <Route path="/management" element={<ManagementPage />} />
      <Route path="/management/performance" element={<ManagementPerformancePage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
    </Routes>
  )
}
