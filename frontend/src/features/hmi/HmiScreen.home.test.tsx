import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { resolveCurrentShift } from './shift'
import {
  activeLine,
  allLinesAvailable,
  availableLine,
  lineStateResponse,
  runState,
} from './hmiTestState'

vi.mock('./api')

afterEach(() => {
  // Scoped to this file's own mock only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  vi.mocked(hmiApi.getHmiConfig).mockReset()
  vi.mocked(hmiApi.getLineState).mockReset()
  vi.mocked(hmiApi.getRunState).mockReset()
  vi.mocked(hmiApi.startRun).mockReset()
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

    expect(screen.getByText('Tonnage Flow Pulse')).toBeInTheDocument()
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

// ==========================================================
// CROSS-DEVICE LINE STATE
// ==========================================================

describe('Home line availability across devices', () => {
  function card(lineName: string) {
    return screen.getByText(lineName).closest('article') as HTMLElement
  }

  const ROVEMA_RUNNING = lineStateResponse([
    activeLine({ line_id: 1, production_line: 'Rovema' }),
    availableLine({ line_id: 2, production_line: 'GIC' }),
    availableLine({ line_id: 3, production_line: 'Guill' }),
  ])

  async function renderHome(lineState = allLinesAvailable()) {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    vi.mocked(hmiApi.getLineState).mockResolvedValue(lineState)
    renderHmi()
    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
  }

  it('shows every configured line with its authoritative availability', async () => {
    await renderHome(ROVEMA_RUNNING)

    await waitFor(() => expect(within(card('Rovema')).getByText('Run Active')).toBeInTheDocument())
    expect(within(card('GIC')).getByText('Available')).toBeInTheDocument()
    expect(within(card('Guill')).getByText('Available')).toBeInTheDocument()
  })

  it('marks a line started on another tablet as Run Active', async () => {
    // Local storage is empty: this device started nothing.
    await renderHome(ROVEMA_RUNNING)

    await waitFor(() => expect(within(card('Rovema')).getByText('Run Active')).toBeInTheDocument())
    expect(within(card('Rovema')).getByText('Started on another device.')).toBeInTheDocument()
    expect(window.localStorage.length).toBe(0)
  })

  it('offers Open Active Run instead of Start Run for an active line', async () => {
    await renderHome(ROVEMA_RUNNING)

    await waitFor(() =>
      expect(
        within(card('Rovema')).getByRole('button', { name: /open active run/i }),
      ).toBeInTheDocument(),
    )
    expect(
      within(card('Rovema')).queryByRole('button', { name: /^start run$/i }),
    ).not.toBeInTheDocument()
  })

  it('opens an active run by reading the full state from the backend', async () => {
    vi.mocked(hmiApi.getRunState).mockResolvedValue(runState())
    await renderHome(ROVEMA_RUNNING)

    await waitFor(() =>
      expect(
        within(card('Rovema')).getByRole('button', { name: /open active run/i }),
      ).toBeInTheDocument(),
    )
    fireEvent.click(within(card('Rovema')).getByRole('button', { name: /open active run/i }))

    await waitFor(() => expect(hmiApi.getRunState).toHaveBeenCalledWith(99))
    // The Active Run screen, driven entirely by the backend response.
    expect(await screen.findByRole('button', { name: /hourly update/i })).toBeInTheDocument()
    // Only now is the run adopted by this device.
    expect(window.localStorage.length).toBeGreaterThan(0)
  })

  it('never lets an active line be started again', async () => {
    await renderHome(ROVEMA_RUNNING)

    await waitFor(() => expect(within(card('Rovema')).getByText('Run Active')).toBeInTheDocument())
    expect(hmiApi.startRun).not.toHaveBeenCalled()
  })

  it('shows planned downtime, changeover and open faults on an active line', async () => {
    await renderHome(
      lineStateResponse([
        activeLine({
          line_id: 1,
          production_line: 'Rovema',
          planned_downtime_active: true,
          changeover_active: true,
          engineering_fault_open: true,
          open_fault_count: 2,
        }),
      ]),
    )

    await waitFor(() =>
      expect(within(card('Rovema')).getByText('Planned downtime')).toBeInTheDocument(),
    )
    expect(within(card('Rovema')).getByText('Changeover')).toBeInTheDocument()
    expect(within(card('Rovema')).getByText('2 engineering faults open')).toBeInTheDocument()
  })

  it('flags a run that has gone quiet as needing an update', async () => {
    await renderHome(
      lineStateResponse([
        activeLine({
          line_id: 1,
          production_line: 'Rovema',
          stale_status: 'stale',
          stale_reason: 'No hourly update for 120 minutes.',
          minutes_since_last_hourly_update: 120,
        }),
      ]),
    )

    await waitFor(() =>
      expect(within(card('Rovema')).getByText('Needs an update')).toBeInTheDocument(),
    )
    expect(
      within(card('Rovema')).getByText('No hourly update for 120 minutes.'),
    ).toBeInTheDocument()
  })

  it('excludes a line that is not configured as active', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue({
      lines: [
        { id: 1, name: 'Rovema', machines: [] },
        { id: 2, name: 'GIC', machines: [] },
      ],
    })
    vi.mocked(hmiApi.getLineState).mockResolvedValue(
      lineStateResponse([
        availableLine({ line_id: 1, production_line: 'Rovema' }),
        availableLine({ line_id: 2, production_line: 'GIC' }),
      ]),
    )
    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    expect(screen.queryByText('Guill')).not.toBeInTheDocument()
  })

  it('says so honestly when line status cannot be loaded, and blocks Start Run', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    vi.mocked(hmiApi.getLineState).mockRejectedValue(new Error('offline'))
    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    expect(await screen.findByText(/line status is unavailable/i)).toBeInTheDocument()
    expect(within(card('Rovema')).getByText('Status unavailable')).toBeInTheDocument()
    expect(within(card('Rovema')).getByRole('button', { name: /^start run$/i })).toBeDisabled()
  })

  it('does not treat empty local storage as proof that a line is free', async () => {
    expect(window.localStorage.length).toBe(0)
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    vi.mocked(hmiApi.getLineState).mockReturnValue(new Promise(() => {}))
    renderHmi()

    await waitFor(() => expect(screen.getByText('Rovema')).toBeInTheDocument())
    expect(within(card('Rovema')).getByText('Checking status…')).toBeInTheDocument()
    expect(within(card('Rovema')).getByRole('button', { name: /^start run$/i })).toBeDisabled()
  })

  it('recovers line status with an explicit retry', async () => {
    vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
    vi.mocked(hmiApi.getLineState).mockRejectedValueOnce(new Error('offline'))
    renderHmi()

    await waitFor(() => expect(screen.getByText(/line status is unavailable/i)).toBeInTheDocument())

    vi.mocked(hmiApi.getLineState).mockResolvedValue(allLinesAvailable())
    fireEvent.click(screen.getByRole('button', { name: /retry line status/i }))

    await waitFor(() => expect(within(card('Rovema')).getByText('Available')).toBeInTheDocument())
  })
})
