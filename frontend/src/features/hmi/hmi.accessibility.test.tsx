import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { availableLine, lineStateResponse } from './hmiTestState'

vi.mock('./api')

afterEach(() => {
  // Scoped to this file's own mock only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  vi.mocked(hmiApi.getHmiConfig).mockReset()
  vi.mocked(hmiApi.getLineState).mockReset()
  window.localStorage.clear()
})

const cssSource = readFileSync(path.resolve(__dirname, 'hmi.css'), 'utf-8')
const tokensSource = readFileSync(path.resolve(__dirname, '../../styles/tokens.css'), 'utf-8')

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
    // The sizes come from the shared design tokens: the HMI must use them,
    // and the tokens must still be 56px (HMI actions) and 44px (minimum).
    expect(cssSource).toMatch(/\.hmi-screen button\s*{[^}]*min-height: var\(--pulse-touch-target-hmi\)/)
    expect(cssSource).toMatch(/\.hmi-screen button\s*{[^}]*min-width: var\(--pulse-touch-target-min\)/)
    expect(tokensSource).toMatch(/--pulse-touch-target-hmi: 56px/)
    expect(tokensSource).toMatch(/--pulse-touch-target-min: 44px/)
  })

  it('a rendered HMI button is a real, keyboard-focusable element', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({
      lines: [{ id: 1, name: 'Rovema', machines: [] }],
    })
    vi.mocked(hmiApi.getLineState).mockResolvedValue(
      lineStateResponse([availableLine({ line_id: 1, production_line: 'Rovema' })]),
    )

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
    vi.mocked(hmiApi.getLineState).mockResolvedValue(
      lineStateResponse([availableLine({ line_id: 1, production_line: 'Rovema' })]),
    )

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
