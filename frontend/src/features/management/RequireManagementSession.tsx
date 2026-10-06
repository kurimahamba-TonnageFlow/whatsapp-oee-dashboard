import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useManagementSession } from './session/useManagementSession'
import { SessionCheck } from './SessionCheck'

/** Renders `children` only with a live Management session; otherwise
 * sends the user to the Management login, remembering where they were
 * going so they return there after signing in. Also takes over the
 * moment a session expires or is signed out while the page is open. */
export function RequireManagementSession({ children }: { children: ReactNode }) {
  const { session, isRestoring, endReason } = useManagementSession()
  const location = useLocation()

  if (isRestoring) return <SessionCheck />

  if (!session) {
    // After a deliberate Log Out, land on the plain sign-in screen.
    const state = endReason === 'signed_out' ? undefined : { from: location.pathname }
    return <Navigate to="/management" replace state={state} />
  }

  return <>{children}</>
}
