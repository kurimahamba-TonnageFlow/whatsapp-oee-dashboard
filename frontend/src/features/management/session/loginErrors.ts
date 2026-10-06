import { ApiRequestError } from '../../../api/client'

/** Maps a failed POST /api/v1/management/login to a safe, user-facing
 * message. Never echoes the PIN, and never shows raw error text. */
export function managementLoginErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return 'Incorrect PIN. Please try again.'
    if (error.status === 429) return 'Too many attempts. Please wait a few minutes and try again.'
    if (error.status === 503) {
      return 'Management sign-in is not set up on the server yet. Please contact your Pulse administrator.'
    }
    if (error.status === 422) return 'Enter your name and the Management PIN.'
    if (error.status === 0) {
      return 'Could not reach the Pulse server. Check your connection and try again.'
    }
    if (error.status >= 500) return 'The Pulse server had a problem. Please try again shortly.'
  }
  return 'Could not sign in. Please try again.'
}
