import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'

// The Management session is kept in sessionStorage so a refresh keeps the
// manager signed in; a sign-in in one test must not restore in the next.
afterEach(() => {
  window.sessionStorage.clear()
})
