import { Outlet } from 'react-router-dom'
import { AppShell } from '../../layouts/AppShell'
import { ManagementSessionBar } from './ManagementSessionBar'
import { ManagementSessionProvider } from './session/ManagementSessionProvider'
import './management.css'

/** Layout route around the whole Management area - /management,
 * /management/performance and the four /dashboard pages. One session
 * provider stays mounted while moving between them (in either visual
 * shell), so a manager signs in once for the whole area. */
export function ManagementSessionRoot() {
  return (
    <ManagementSessionProvider>
      <Outlet />
    </ManagementSessionProvider>
  )
}

/** The light AppShell used by /management and /management/performance.
 * The dashboard pages use their own dark shell (DashboardLayout). */
export function ManagementLayout() {
  return (
    <AppShell>
      <ManagementSessionBar />
      <Outlet />
    </AppShell>
  )
}
