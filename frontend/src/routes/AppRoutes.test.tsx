import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppRoutes } from './AppRoutes'

// These tests are about routing, not API connectivity - every page
// renders AppShell, which includes ApiStatus. Mocking the client here
// keeps these tests isolated and avoids an unrelated, unmocked network
// call resolving after the test body finishes.
// ApiRequestError stays the real class - the Management session code
// imports it.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: vi.fn(() => new Promise(() => {})) },
  }
})

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

describe('AppRoutes', () => {
  it('redirects / to /hmi', () => {
    renderAt('/')

    // /hmi is the real operator HMI (Stage 4) - its home screen shows
    // this heading while the config fetch (mocked as never-resolving
    // above) is pending.
    expect(
      screen.getByRole('heading', { name: /tablet sign in/i }),
    ).toBeInTheDocument()
  })

  it('renders the real HMI home screen at /hmi', () => {
    renderAt('/hmi')

    // Appears once in AppShell's shared header and once in the HMI's
    // own home-screen brand line.
    expect(screen.getAllByText('Tonnage Flow Pulse')).toHaveLength(1)
    expect(
      screen.getByRole('heading', { name: /tablet sign in/i }),
    ).toBeInTheDocument()
  })

  it('renders the Management sign-in screen at /management (Stage 6C1)', () => {
    renderAt('/management')

    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
  })

  it.each([
    ['/management/performance', /technician performance/i],
    ['/dashboard', /production dashboard/i],
  ])('sends a signed-out user from %s to the Management sign-in', (path, destination) => {
    renderAt(path)

    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(screen.getByText(destination)).toBeInTheDocument()
  })

  it('renders the real Engineering sign-in screen at /engineering (Stage 5B)', () => {
    renderAt('/engineering')

    expect(screen.getByRole('heading', { name: /engineering sign in/i })).toBeInTheDocument()
  })
})
