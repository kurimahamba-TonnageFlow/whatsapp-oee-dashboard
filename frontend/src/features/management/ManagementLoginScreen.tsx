import { useState } from 'react'
import * as managementApi from './api'
import { managementLoginErrorMessage } from './session/loginErrors'
import { useManagementSession } from './session/useManagementSession'

const MAX_MANAGER_NAME_LENGTH = 100

interface ManagementLoginScreenProps {
  /** Set when a protected page sent the user here, e.g. "Production dashboard". */
  destinationLabel?: string | null
}

export function ManagementLoginScreen({ destinationLabel }: ManagementLoginScreenProps) {
  const { signIn, notice } = useManagementSession()
  const [managerName, setManagerName] = useState('')
  const [pin, setPin] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const trimmedName = managerName.trim()

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()

    if (!trimmedName || !pin || isSubmitting) return

    setIsSubmitting(true)
    setErrorMessage(null)

    managementApi
      .login({ pin, manager_name: trimmedName })
      .then((response) => {
        signIn(response)
      })
      .catch((error: unknown) => {
        setErrorMessage(managementLoginErrorMessage(error))
      })
      .finally(() => {
        // Cleared on every attempt, success or failure - the PIN never
        // lingers in a form field and is never stored anywhere.
        setPin('')
        setIsSubmitting(false)
      })
  }

  return (
    <section className="management-login" aria-labelledby="management-login-heading">
      <div className="management-panel management-login__panel">
        <p className="management-eyebrow">Tonnage Flow Pulse</p>
        <h1 id="management-login-heading">Management Sign In</h1>

        {destinationLabel ? (
          <p className="management-notice" role="status">
            Sign in to open {destinationLabel}.
          </p>
        ) : (
          <p className="management-muted">
            Sign in with the Management PIN to manage factory setup, runs and targets.
          </p>
        )}

        {notice && (
          <p className="management-notice" role="status">
            {notice}
          </p>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <label className="management-field" htmlFor="management-manager-name">
            Your name
            <input
              id="management-manager-name"
              type="text"
              autoComplete="off"
              maxLength={MAX_MANAGER_NAME_LENGTH}
              value={managerName}
              onChange={(event) => setManagerName(event.target.value)}
              required
            />
          </label>

          <label className="management-field" htmlFor="management-pin">
            Management PIN
            <input
              id="management-pin"
              type="password"
              autoComplete="off"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              required
            />
          </label>

          {errorMessage && (
            <p className="management-alert" role="alert">
              {errorMessage}
            </p>
          )}

          <button
            type="submit"
            className="management-primary-button"
            disabled={isSubmitting || !trimmedName || !pin}
          >
            {isSubmitting ? 'Signing In…' : 'Sign In'}
          </button>
        </form>
      </div>
    </section>
  )
}
