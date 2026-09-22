import { useState } from 'react'
import { LoginScreen } from './LoginScreen'
import { Workspace } from './Workspace'
import type { EngineeringLoginResponse } from './types'

interface EngineeringSession {
  token: string
  engineerName: string
}

/**
 * Owns the Engineering session for as long as this component stays
 * mounted - a plain useState, held only in this component's React
 * (JS-memory) state. Never written to localStorage, sessionStorage,
 * IndexedDB or a cookie, so a browser refresh always remounts this
 * component with session = null, requiring sign-in again.
 */
export function EngineeringScreen() {
  const [session, setSession] = useState<EngineeringSession | null>(null)
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null)

  function handleLoginSuccess(response: EngineeringLoginResponse) {
    setSessionExpiredMessage(null)
    setSession({ token: response.token, engineerName: response.engineer_name })
  }

  function handleLogout() {
    setSession(null)
  }

  function handleSessionExpired() {
    setSession(null)
    setSessionExpiredMessage('Your Engineering session has expired. Please sign in again.')
  }

  if (!session) {
    return (
      <LoginScreen onLoginSuccess={handleLoginSuccess} sessionExpiredMessage={sessionExpiredMessage} />
    )
  }

  return (
    <Workspace
      token={session.token}
      engineerName={session.engineerName}
      onLogout={handleLogout}
      onSessionExpired={handleSessionExpired}
    />
  )
}
