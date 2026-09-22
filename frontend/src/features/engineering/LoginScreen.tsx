import { useState } from 'react'
import { Link } from 'react-router-dom'
import * as engineeringApi from './api'
import { ApiRequestError } from '../../api/client'
import { ApiStatus } from '../../components/ApiStatus'
import { ENGINEERS } from './constants'
import type { EngineeringLoginResponse } from './types'

interface LoginScreenProps {
  onLoginSuccess: (session: EngineeringLoginResponse) => void
  sessionExpiredMessage?: string | null
}

function safeLoginErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return 'Incorrect PIN. Please try again.'
    if (error.status === 429) return 'Too many attempts. Please wait a few minutes and try again.'
    if (error.status === 503) return 'Engineering sign-in is not available right now. Please try again shortly.'
    if (error.status === 422) return 'Select an engineer name from the list.'
    return error.message
  }
  return 'Could not sign in. Please try again.'
}

export function LoginScreen({ onLoginSuccess, sessionExpiredMessage }: LoginScreenProps) {
  const [engineerName, setEngineerName] = useState('')
  const [pin, setPin] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()

    if (!engineerName || !pin || isSubmitting) return

    setIsSubmitting(true)
    setErrorMessage(null)

    engineeringApi
      .login({ pin, engineer_name: engineerName })
      .then((session) => {
        onLoginSuccess(session)
      })
      .catch((error: unknown) => {
        setErrorMessage(safeLoginErrorMessage(error))
      })
      .finally(() => {
        // Cleared on every attempt, success or failure - the PIN never
        // lingers in a form field.
        setPin('')
        setIsSubmitting(false)
      })
  }

  return (
    <div className="engineering-screen engineering-login">
      <div className="engineering-login__panel">
        <p className="engineering-login__brand">Tonnage Flow Pulse</p>
        <h1>Engineering Sign In</h1>
        <ApiStatus />

        {sessionExpiredMessage && (
          <p className="engineering-inline-error" role="alert">
            {sessionExpiredMessage}
          </p>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <label className="engineering-field" htmlFor="engineering-engineer-name">
            Engineer
            <select
              id="engineering-engineer-name"
              value={engineerName}
              onChange={(event) => setEngineerName(event.target.value)}
              required
              autoComplete="off"
            >
              <option value="">Select your name…</option>
              {ENGINEERS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label className="engineering-field" htmlFor="engineering-pin">
            Engineering PIN
            <input
              id="engineering-pin"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              required
            />
          </label>

          {errorMessage && (
            <p className="engineering-inline-error" role="alert">
              {errorMessage}
            </p>
          )}

          <div className="engineering-login__actions">
            <button
              type="submit"
              className="engineering-primary-button"
              disabled={isSubmitting || !engineerName || !pin}
            >
              {isSubmitting ? 'Signing In…' : 'Sign In'}
            </button>
          </div>
        </form>

        <Link to="/hmi" className="engineering-back-link">
          ← Back to HMI
        </Link>
      </div>
    </div>
  )
}
