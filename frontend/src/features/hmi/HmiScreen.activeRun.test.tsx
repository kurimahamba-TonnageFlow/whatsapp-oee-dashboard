import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { ApiRequestError } from '../../api/client'
import { saveActiveRun } from './activeRunStorage'
import type { ActiveRunRecord } from './types'

vi.mock('./api')

afterEach(() => {
  // Scoped to this file's own mocks only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  vi.mocked(hmiApi.getHmiConfig).mockReset()
  vi.mocked(hmiApi.completeRun).mockReset()
  window.localStorage.clear()
})

const SAMPLE_RUN: ActiveRunRecord = {
  runId: 99,
  startedAtIso: new Date(Date.now() - 60 * 60_000).toISOString(),
  form: {
    productionLine: 'Rovema',
    lineTechnician: 'Liam',
    shift: 'Days',
    customer: 'Asda',
    product: 'White Basmati',
    packWeightLabel: '1kg',
    packWeightKg: '1',
    packsPerCase: '8',
    packType: '1 kg × 8',
    targetSpeedPpm: '120',
    casesPerPallet: '220',
    palletsRemaining: '38',
    previousRunCompleted: '0',
  },
  totalPalletsCompleted: 0,
  plannedDowntimeMinutes: 0,
  unplannedDowntimeMinutes: 0,
}

const CONFIG_WITH_MACHINE = {
  lines: [
    {
      id: 1,
      name: 'Rovema',
      machines: [
        {
          id: 10,
          name: 'BV1',
          buttons: [
            {
              id: 20,
              name: 'Film Jam',
              event_type: 'unplanned_fault' as const,
              ownership: 'Production' as const,
              fault_category: null,
            },
          ],
        },
      ],
    },
  ],
}

function renderActiveRun(run: ActiveRunRecord = SAMPLE_RUN) {
  saveActiveRun(run)
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(CONFIG_WITH_MACHINE)
  return render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('HmiScreen Active Run screen', () => {
  it('restores and displays the active run on load (refresh-safe)', async () => {
    renderActiveRun()
    // Flush the background config fetch HmiScreen always issues on mount.
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument()
    expect(screen.getByText('Liam')).toBeInTheDocument()
    expect(screen.getByText('Days')).toBeInTheDocument()
    expect(screen.getByText('120 packs/min')).toBeInTheDocument()
    expect(screen.getByText(/asda/i)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    // planned and unplanned downtime both start at 0 minutes
    expect(screen.getAllByText('0 min')).toHaveLength(2)
  })

  it('runs the Hourly Update workflow end to end and updates the Active Run totals', async () => {
    renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /hourly update/i }))
    expect(screen.getByRole('heading', { name: /hourly update/i })).toBeInTheDocument()
    expect(screen.getByText('0 pallets')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/pallets produced this period/i), {
      target: { value: '5' },
    })
    fireEvent.click(screen.getByRole('button', { name: /confirm update/i }))

    await waitFor(() => expect(screen.getByText('✓ Update recorded')).toBeInTheDocument())
    expect(screen.getByText('5 pallets')).toBeInTheDocument()

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument(),
      { timeout: 3000 },
    )
    expect(screen.getByText('5')).toBeInTheDocument() // pallets completed on Active Run screen
  })

  it('runs the Planned Downtime workflow: start, show elapsed, confirm end, return to Active Run', async () => {
    renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    expect(screen.getByRole('heading', { name: /planned downtime$/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Label Change' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /planned downtime — label change/i })).toBeInTheDocument(),
    )
    expect(screen.getByText(/elapsed:/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /end planned downtime/i }))
    expect(screen.getByText(/end planned downtime now/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /yes, end downtime/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument(),
    )
  })

  it('runs the Report to Engineer workflow using configured machines/buttons and shows a confirmation', async () => {
    renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /report to engineer/i }))
    expect(screen.getByRole('heading', { name: /report to engineer/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: 'Film Jam' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() =>
      expect(screen.getByText('✓ Reported to Engineering')).toBeInTheDocument(),
    )
    expect(screen.getByText(/reference: local-fixture-fault-/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /back to active run/i }))
    expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument()
  })

  it('shows the Complete Run warning and completes successfully', async () => {
    vi.mocked(hmiApi.completeRun).mockResolvedValue({
      status: 'success',
      message: 'Run completed',
      run_id: 99,
      production_line: 'Rovema',
      run_status: 'Completed',
    })

    renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /complete run/i }))
    expect(screen.getByText(/this will close the active run/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /confirm complete run/i }))

    await waitFor(() => expect(screen.getByText('✓ RUN COMPLETED')).toBeInTheDocument())
    expect(hmiApi.completeRun).toHaveBeenCalledWith(99)

    fireEvent.click(screen.getByRole('button', { name: /back to home/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /select a production line/i })).toBeInTheDocument(),
    )
  })

  it.each([
    [404, 'This run could not be found.'],
    [409, 'This run has already been completed.'],
    [503, 'The system is temporarily unavailable. Please try again.'],
  ])('shows a safe message (not a raw server error) for a %i complete-run failure', async (status, expected) => {
    vi.mocked(hmiApi.completeRun).mockRejectedValue(
      new ApiRequestError(status, 'raw backend detail text'),
    )

    renderActiveRun()
    fireEvent.click(screen.getByRole('button', { name: /complete run/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm complete run/i }))

    await waitFor(() => expect(screen.getByText(expected)).toBeInTheDocument())
  })

  it('Exit or Restart requires confirmation and never calls a completion or force-close endpoint', async () => {
    renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /exit or restart run/i }))
    expect(screen.getByText(/this run will stay active in the system/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /exit to home/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /select a production line/i })).toBeInTheDocument(),
    )
    expect(hmiApi.completeRun).not.toHaveBeenCalled()
  })
})
