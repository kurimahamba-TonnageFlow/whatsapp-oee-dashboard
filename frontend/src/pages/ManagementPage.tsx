import { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ManagementHome } from '../features/management/ManagementHome'
import { ManagementLoginScreen } from '../features/management/ManagementLoginScreen'
import { SessionCheck } from '../features/management/SessionCheck'
import { protectedDestinationFrom } from '../features/management/destinations'
import { useManagementSession } from '../features/management/session/useManagementSession'

/** /management - the Management sign-in, then the Management home.
 * Rendered inside ManagementLayout (AppShell + shared session). */
export function ManagementPage() {
  const { session, isRestoring, endReason, acknowledgeSignOut } = useManagementSession()
  const location = useLocation()
  const destination = protectedDestinationFrom(location.state)

  // The sign-out redirect has landed here; from now on a protected page
  // the manager opens is remembered again for after sign-in.
  useEffect(() => {
    if (!session && endReason === 'signed_out') acknowledgeSignOut()
  }, [session, endReason, acknowledgeSignOut])

  if (isRestoring) return <SessionCheck />

  if (!session) {
    return <ManagementLoginScreen destinationLabel={destination?.label ?? null} />
  }

  // Signed in on the way to a protected page: go straight there, without
  // drawing the Management home first.
  if (destination) {
    return <Navigate to={destination.path} replace />
  }

  return <ManagementHome />
}
