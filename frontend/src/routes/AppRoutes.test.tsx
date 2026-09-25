import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppRoutes } from './AppRoutes'

// These tests are about routing, not API connectivity - every page
// renders AppShell, which includes ApiStatus. Mocking the client here
// keeps these tests isolated and avoids an unrelated, unmocked network
// call resolving after the test body finishes.
vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn(() => new Promise(() => {})) },
}))

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
      screen.getByRole('heading', { name: /select a production line/i }),
    ).toBeInTheDocument()
  })

  it('renders the real HMI home screen at /hmi', () => {
    renderAt('/hmi')

    // Appears once in AppShell's shared header and once in the HMI's
    // own home-screen brand line.
    expect(screen.getAllByText('Tonnage Flow Pulse')).toHaveLength(2)
    expect(
      screen.getByRole('heading', { name: /select a production line/i }),
    ).toBeInTheDocument()
  })

  it.each([
    ['/management', /^management$/i],
    ['/management/performance', /technician performance/i],
    ['/dashboard', /^dashboard$/i],
  ])('renders a placeholder heading for %s', (path, expectedHeading) => {
    renderAt(path)

    expect(screen.getByRole('heading', { name: expectedHeading })).toBeInTheDocument()
  })

  it('renders the real Engineering sign-in screen at /engineering (Stage 5B)', () => {
    renderAt('/engineering')

    expect(screen.getByRole('heading', { name: /engineering sign in/i })).toBeInTheDocument()
  })
})
