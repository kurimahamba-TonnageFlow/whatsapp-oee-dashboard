import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'

vi.mock('./api')

afterEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
})

const cssSource = readFileSync(path.resolve(__dirname, 'hmi.css'), 'utf-8')

describe('HMI accessibility and responsive foundations', () => {
  it('defines a visible keyboard focus style (not hover-only)', () => {
    expect(cssSource).toMatch(/:focus-visible\s*{/)
    expect(cssSource).toContain('outline: 3px solid var(--hmi-focus)')
  })

  it('defines a mobile breakpoint (~375px) and a tablet-landscape breakpoint (~1024px)', () => {
    expect(cssSource).toMatch(/@media \(max-width: 480px\)/)
    expect(cssSource).toMatch(/@media \(min-width: 1024px\)/)
  })

  it('gives every button a minimum 44px touch target', () => {
    expect(cssSource).toMatch(/\.hmi-screen button\s*{[^}]*min-height: 56px/)
    expect(cssSource).toMatch(/\.hmi-screen button\s*{[^}]*min-width: 44px/)
  })

  it('a rendered HMI button is a real, keyboard-focusable element', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({
      lines: [{ id: 1, name: 'Rovema', machines: [] }],
    })

    render(
      <MemoryRouter initialEntries={['/hmi']}>
        <Routes>
          <Route path="/hmi" element={<HmiScreen />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    const button = screen.getByRole('button', { name: /start run/i })
    expect(button.tagName).toBe('BUTTON')

    button.focus()
    expect(document.activeElement).toBe(button)
  })

  it('never disables the Start Run button click handling behind a hover-only affordance', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({
      lines: [{ id: 1, name: 'Rovema', machines: [] }],
    })

    render(
      <MemoryRouter initialEntries={['/hmi']}>
        <Routes>
          <Route path="/hmi" element={<HmiScreen />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /start run/i }))

    expect(screen.getByRole('heading', { name: /start run — rovema/i })).toBeInTheDocument()
  })
})
