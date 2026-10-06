import { useNavigate } from 'react-router-dom'
import { formatSessionEnd } from './destinations'
import { useManagementSession } from './session/useManagementSession'

/** Shown on every Management-area page while signed in: who is signed
 * in, when the session ends, and a clear Log Out control. */
export function ManagementSessionBar() {
  const { session, signOut } = useManagementSession()
  const navigate = useNavigate()

  if (!session) return null

  const endsAt = formatSessionEnd(session.expiresAt)

  function handleLogOut() {
    signOut()
    navigate('/management', { replace: true })
  }

  return (
    <div className="management-session-bar" role="region" aria-label="Management session">
      <p className="management-session-bar__text">
        Signed in as <strong>{session.managerName}</strong>
        {endsAt && <span className="management-muted"> · Session ends {endsAt}</span>}
      </p>
      <button type="button" className="management-secondary-button" onClick={handleLogOut}>
        Log Out
      </button>
    </div>
  )
}
