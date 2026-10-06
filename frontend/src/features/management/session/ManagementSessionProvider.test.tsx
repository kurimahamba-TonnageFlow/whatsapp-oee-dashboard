import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError } from '../../../api/client'
import * as managementApi from '../api'
import { managementLoginErrorMessage } from './loginErrors'
import { ManagementSessionProvider } from './ManagementSessionProvider'
import type { ManagementSessionContextValue } from './managementSessionContext'
import { useManagementSession } from './useManagementSession'

vi.mock('../api')

beforeEach(() => {
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
})

afterEach(() => {
  // Unmount first so an unmount-time revoke lands on this test's mock.
  cleanup()
  vi.mocked(managementApi.logout).mockReset()
})

const LOGIN = {
  status: 'success',
  token: 'unit-token',
  manager_name: 'Kuri',
  expires_at: '2099-01-01T00:00:00+00:00',
}

/** Exposes the context value to the test and renders its state. */
function Probe({ onValue }: { onValue: (value: ManagementSessionContextValue) => void }) {
  const value = useManagementSession()
  onValue(value)
  return (
    <p>
      {value.session ? `signed in: ${value.session.managerName}` : 'signed out'} | {value.notice ?? ''}
    </p>
  )
}

function renderProvider() {
  let latest!: ManagementSessionContextValue
  const utils = render(
    <ManagementSessionProvider>
      <Probe onValue={(v) => (latest = v)} />
    </ManagementSessionProvider>,
  )
  return { ...utils, current: () => latest }
}

describe('ManagementSessionProvider', () => {
  it('starts signed out and stores only token, name and expiry on sign-in', () => {
    const { current } = renderProvider()
    expect(screen.getByText(/signed out/)).toBeInTheDocument()

    act(() => current().signIn(LOGIN))

    expect(screen.getByText(/signed in: Kuri/)).toBeInTheDocument()
    expect(current().session).toEqual({
      token: 'unit-token',
      managerName: 'Kuri',
      expiresAt: '2099-01-01T00:00:00+00:00',
    })
  })

  it('waits out a deadline longer than the setTimeout limit instead of expiring at once', () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2026-09-25T10:00:00Z'))
      const { current } = renderProvider()
      // 40 days: beyond setTimeout's ~24.8-day ceiling.
      act(() => current().signIn({ ...LOGIN, expires_at: '2026-11-04T10:00:00+00:00' }))

      act(() => {
        vi.advanceTimersByTime(30 * 24 * 60 * 60 * 1000)
      })
      expect(current().session).not.toBeNull()

      act(() => {
        vi.advanceTimersByTime(10 * 24 * 60 * 60 * 1000)
      })
      expect(current().session).toBeNull()
      expect(current().notice).toMatch(/session has expired/i)
    } finally {
      vi.useRealTimers()
    }
  })

  it('handleAuthError expires the session on a 401 and reports it handled', () => {
    const { current } = renderProvider()
    act(() => current().signIn(LOGIN))

    let handled = false
    act(() => {
      handled = current().handleAuthError(new ApiRequestError(401, 'expired'))
    })

    expect(handled).toBe(true)
    expect(current().session).toBeNull()
    expect(current().notice).toMatch(/session has expired/i)
    // The server already rejected the token - nothing to revoke.
    expect(managementApi.logout).not.toHaveBeenCalled()
  })

  it.each([
    new ApiRequestError(403, 'forbidden'),
    new ApiRequestError(500, 'server'),
    new ApiRequestError(0, 'offline'),
    new Error('other'),
  ])('handleAuthError leaves the session alone for %s', (error) => {
    const { current } = renderProvider()
    act(() => current().signIn(LOGIN))

    let handled = true
    act(() => {
      handled = current().handleAuthError(error)
    })

    expect(handled).toBe(false)
    expect(current().session).not.toBeNull()
  })

  it('revokes a live session server-side when the provider unmounts', () => {
    vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
    const { current, unmount } = renderProvider()
    act(() => current().signIn(LOGIN))

    unmount()

    expect(managementApi.logout).toHaveBeenCalledWith('unit-token')
  })

  it('does not call logout on unmount when nobody is signed in', () => {
    const { unmount } = renderProvider()

    unmount()

    expect(managementApi.logout).not.toHaveBeenCalled()
  })

  it('throws a clear error when used outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Probe onValue={() => {}} />)).toThrow(/inside ManagementSessionProvider/)
    spy.mockRestore()
  })
})

describe('managementLoginErrorMessage', () => {
  it.each([
    [401, 'Incorrect PIN. Please try again.'],
    [429, 'Too many attempts. Please wait a few minutes and try again.'],
    [503, 'Management sign-in is not set up on the server yet. Please contact your Pulse administrator.'],
    [422, 'Enter your name and the Management PIN.'],
    [0, 'Could not reach the Pulse server. Check your connection and try again.'],
    [502, 'The Pulse server had a problem. Please try again shortly.'],
    [400, 'Could not sign in. Please try again.'],
  ])('maps HTTP %s to a safe message', (status, expected) => {
    expect(managementLoginErrorMessage(new ApiRequestError(status, 'server detail text'))).toBe(expected)
  })

  it('never echoes the server detail or a thrown message', () => {
    expect(managementLoginErrorMessage(new ApiRequestError(400, 'secret detail'))).not.toMatch(/secret/)
    expect(managementLoginErrorMessage(new Error('secret'))).toBe('Could not sign in. Please try again.')
  })
})
