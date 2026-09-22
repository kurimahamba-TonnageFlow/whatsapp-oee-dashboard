import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EngineeringScreen } from './EngineeringScreen'
import * as engineeringApi from './api'
import { ApiRequestError, apiClient } from '../../api/client'

vi.mock('./api')

// ApiStatus (rendered by LoginScreen) calls the real apiClient's
// GET /health directly - stub only that method so it never resolves
// during a test, mirroring AppRoutes.test.tsx's approach, while
// keeping ApiRequestError (used by these tests) as the real class.
vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: vi.fn(() => new Promise(() => {})) },
  }
})

afterEach(() => {
  // Scoped to this file's own mocks only, never vi.resetAllMocks() -
  // see the note by each "mounts Workspace" test below for why a
  // pending effect must never still be in flight when this runs.
  vi.mocked(engineeringApi.login).mockReset()
  vi.mocked(engineeringApi.logout).mockReset()
  vi.mocked(engineeringApi.getFaults).mockReset()
  // Cleared, not reset: apiClient.get's perpetually-pending default
  // implementation (set in the vi.mock('../../api/client', ...) factory
  // above, for ApiStatus's health check) must survive every test in
  // this file - no test here ever reconfigures it.
  vi.mocked(apiClient.get).mockClear()
  window.localStorage.clear()
  window.sessionStorage.clear()
})

function renderEngineering() {
  return render(
    <MemoryRouter initialEntries={['/engineering']}>
      <Routes>
        <Route path="/engineering" element={<EngineeringScreen />} />
        <Route path="/hmi" element={<div>HMI placeholder marker</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const LOGIN_SUCCESS = {
  status: 'success',
  token: 'test-token-abc123',
  engineer_name: 'Alfie',
  expires_at: '2026-09-18T15:00:00+00:00',
}

function signIn() {
  fireEvent.change(screen.getByLabelText(/^engineer$/i), { target: { value: 'Alfie' } })
  fireEvent.change(screen.getByLabelText(/engineering pin/i), { target: { value: '1234' } })
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
}

describe('Engineering authentication', () => {
  it('renders the login screen with engineer selection and a masked PIN field', () => {
    renderEngineering()

    expect(screen.getByRole('heading', { name: /engineering sign in/i })).toBeInTheDocument()

    for (const name of ['Aaron', 'Yago', 'Steve', 'Dan', 'Kuri', 'Alfie']) {
      expect(screen.getByRole('option', { name })).toBeInTheDocument()
    }

    expect(screen.getByLabelText(/engineering pin/i)).toHaveAttribute('type', 'password')
  })

  it('provides a Back to HMI link that navigates to /hmi', () => {
    renderEngineering()

    fireEvent.click(screen.getByRole('link', { name: /back to hmi/i }))

    expect(screen.getByText('HMI placeholder marker')).toBeInTheDocument()
  })

  it('signs in successfully and shows the workspace for the selected engineer', async () => {
    vi.mocked(engineeringApi.login).mockResolvedValue(LOGIN_SUCCESS)
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderEngineering()
    signIn()

    await waitFor(() => expect(screen.getByText(/signed in as alfie/i)).toBeInTheDocument())
    expect(engineeringApi.login).toHaveBeenCalledWith({ pin: '1234', engineer_name: 'Alfie' })
    // "Signed in as Alfie" renders on Workspace's very first pass,
    // before its useFaultPolling effect has necessarily fired - without
    // this, the test can end (and afterEach's mockReset() run) while
    // that mount effect is still pending, so it fires later against an
    // already-reset mock. Waiting for the actual call closes that
    // window deterministically, the same way every other test in this
    // file that asserts on faults-derived UI already does implicitly.
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalled())
  })

  it('shows a safe message for an incorrect PIN (401)', async () => {
    vi.mocked(engineeringApi.login).mockRejectedValue(new ApiRequestError(401, 'Incorrect PIN.'))

    renderEngineering()
    signIn()

    await waitFor(() => expect(screen.getByText(/incorrect pin/i)).toBeInTheDocument())
  })

  it('shows a safe message during a login lockout (429)', async () => {
    vi.mocked(engineeringApi.login).mockRejectedValue(
      new ApiRequestError(429, 'Too many failed attempts. Please try again later.'),
    )

    renderEngineering()
    signIn()

    await waitFor(() => expect(screen.getByText(/too many attempts/i)).toBeInTheDocument())
  })

  it('shows a safe message when the backend Engineering PIN is not configured (503)', async () => {
    vi.mocked(engineeringApi.login).mockRejectedValue(
      new ApiRequestError(503, 'Engineering login is not configured.'),
    )

    renderEngineering()
    signIn()

    await waitFor(() => expect(screen.getByText(/not available right now/i)).toBeInTheDocument())
  })

  it('clears the PIN field after every submission attempt', async () => {
    vi.mocked(engineeringApi.login).mockRejectedValue(new ApiRequestError(401, 'Incorrect PIN.'))

    renderEngineering()
    signIn()

    await waitFor(() => {
      const pinInput = screen.getByLabelText(/engineering pin/i) as HTMLInputElement
      expect(pinInput.value).toBe('')
    })
  })

  it('never writes the session token to localStorage or sessionStorage', async () => {
    vi.mocked(engineeringApi.login).mockResolvedValue(LOGIN_SUCCESS)
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderEngineering()
    signIn()

    await waitFor(() => expect(screen.getByText(/signed in as alfie/i)).toBeInTheDocument())
    // See the note in "signs in successfully..." above: waiting for the
    // actual call ensures Workspace's mount effect has fired before
    // this test ends and afterEach's mockReset() runs.
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalled())

    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('logs out and returns to the login screen', async () => {
    vi.mocked(engineeringApi.login).mockResolvedValue(LOGIN_SUCCESS)
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(engineeringApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })

    renderEngineering()
    signIn()
    await waitFor(() => expect(screen.getByText(/signed in as alfie/i)).toBeInTheDocument())
    // See the note in "signs in successfully..." above: waiting for the
    // actual call ensures Workspace's mount effect has fired before
    // this test moves on (and, at the end, before afterEach's
    // mockReset() runs).
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: /log out/i }))

    expect(await screen.findByRole('heading', { name: /engineering sign in/i })).toBeInTheDocument()
    expect(engineeringApi.logout).toHaveBeenCalledWith('test-token-abc123')
  })

  it('requires login again after a fresh mount (simulating a browser refresh)', async () => {
    vi.mocked(engineeringApi.login).mockResolvedValue(LOGIN_SUCCESS)
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    const { unmount } = renderEngineering()
    signIn()
    await waitFor(() => expect(screen.getByText(/signed in as alfie/i)).toBeInTheDocument())
    // See the note in "signs in successfully..." above: waiting for the
    // actual call ensures Workspace's mount effect has fired before
    // this test's own explicit unmount() (and, either way, before
    // afterEach's mockReset() runs).
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalled())

    unmount()
    renderEngineering()

    expect(screen.getByRole('heading', { name: /engineering sign in/i })).toBeInTheDocument()
  })

  it('returns to login with a safe message when a request returns 401 after sign-in', async () => {
    vi.mocked(engineeringApi.login).mockResolvedValue(LOGIN_SUCCESS)
    vi.mocked(engineeringApi.getFaults).mockRejectedValue(
      new ApiRequestError(401, 'Engineering session is invalid or has expired.'),
    )

    renderEngineering()
    signIn()

    await waitFor(() =>
      expect(
        screen.getByText('Your Engineering session has expired. Please sign in again.'),
      ).toBeInTheDocument(),
    )
  })
})
