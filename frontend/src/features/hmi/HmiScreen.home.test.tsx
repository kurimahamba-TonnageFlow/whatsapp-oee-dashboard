import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { resolveCurrentShift } from './shift'

vi.mock('./api')

afterEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
})

function renderHmi() {
  return render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
        <Route path="/engineering" element={<div>Engineering placeholder marker</div>} />
        <Route path="/management" element={<div>Management placeholder marker</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const READY_CONFIG = {
  lines: [
    { id: 1, name: 'Rovema', machines: [] },
    { id: 2, name: 'GIC', machines: [] },
    { id: 3, name: 'Guill', machines: [] },
  ],
}

describe('HmiScreen home', () => {
  it('renders the HMI home screen with the brand and line selection heading', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)

    renderHmi()

    expect(screen.getByText('TonnageFlow Pulse')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /select a production line/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
  })

  it('resolves and displays the current shift', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    const expectedShift = resolveCurrentShift()

    renderHmi()

    expect(screen.getByText(`Current shift: ${expectedShift.label}`)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
  })

  it('shows a loading state, then loads lines from GET /api/v1/hmi/config', async () => {
    let resolveConfig: (value: typeof READY_CONFIG) => void = () => {}
    vi.mocked(hmiApi.getHmiConfig).mockReturnValue(
      new Promise((resolve) => {
        resolveConfig = resolve
      }),
    )

    renderHmi()

    expect(screen.getByText(/loading production lines/i)).toBeInTheDocument()

    resolveConfig(READY_CONFIG)
    await waitFor(() => expect(screen.getByText('GIC')).toBeInTheDocument())
    expect(screen.getByText('Guill')).toBeInTheDocument()
  })

  it('never shows a disabled line - only what the config endpoint returns', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({
      lines: [{ id: 1, name: 'Rovema', machines: [] }],
    })

    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    expect(screen.queryByText('GIC')).not.toBeInTheDocument()
    expect(screen.queryByText('Guill')).not.toBeInTheDocument()
  })

  it('shows an empty-configuration message when no lines are returned', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({ lines: [] })

    renderHmi()

    await waitFor(() =>
      expect(screen.getByText(/no production lines are configured yet/i)).toBeInTheDocument(),
    )
  })

  it('shows API unavailable with a Retry button, which reloads on click', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockRejectedValueOnce(new Error('network down'))

    renderHmi()

    await waitFor(() =>
      expect(screen.getByText(/could not load production lines/i)).toBeInTheDocument(),
    )

    vi.mocked(hmiApi.getHmiConfig).mockResolvedValueOnce(READY_CONFIG)
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
  })

  it('navigates to /engineering when Engineering is pressed', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /^engineering$/i }))

    expect(await screen.findByText('Engineering placeholder marker')).toBeInTheDocument()
  })

  it('navigates to /management when Management is pressed', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /^management$/i }))

    expect(await screen.findByText('Management placeholder marker')).toBeInTheDocument()
  })
})
