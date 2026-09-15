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

    expect(screen.getByRole('heading', { name: /^hmi$/i })).toBeInTheDocument()
  })

  it.each([
    ['/hmi', /^hmi$/i],
    ['/engineering', /^engineering$/i],
    ['/management', /^management$/i],
    ['/management/performance', /technician performance/i],
    ['/dashboard', /^dashboard$/i],
  ])('renders a placeholder heading for %s', (path, expectedHeading) => {
    renderAt(path)

    expect(screen.getByRole('heading', { name: expectedHeading })).toBeInTheDocument()
  })
})
