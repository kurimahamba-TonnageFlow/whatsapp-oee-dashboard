import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { ApiRequestError } from '../../api/client'
import { saveActiveRun } from './activeRunStorage'
import { HMI_CONFIG, runState } from './hmiTestState'
import type { FaultReportResponse } from './types'

vi.mock('./api')

const MOCKED = ['getHmiConfig', 'getRunState', 'reportFault'] as const

afterEach(() => {
  MOCKED.forEach((name) => vi.mocked(hmiApi[name]).mockReset())
  window.localStorage.clear()
})

beforeEach(() => {
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(HMI_CONFIG)
})

function faultResponse(overrides: Partial<FaultReportResponse> = {}): FaultReportResponse {
  return {
    status: 'success',
    downtime_event_id: 41,
    production_run_id: 99,
    production_line: 'Rovema',
    fault_id: 4,
    machine: 'BV1',
    reason: 'Film Jam',
    reported_by: 'Liam',
    production_status: 'Ongoing',
    engineering_status: 'Not Started',
    opened_at: '2026-01-12T08:00:00+00:00',
    ...overrides,
  }
}

async function openReportScreen() {
  saveActiveRun({ runId: 99, productionLine: 'Rovema' })
  vi.mocked(hmiApi.getRunState).mockResolvedValue(runState())

  render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
      </Routes>
    </MemoryRouter>,
  )

  await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: /report to engineer/i }))
}

describe('Report to Engineer', () => {
  it('sends the configured machine and fault button', async () => {
    vi.mocked(hmiApi.reportFault).mockResolvedValue(faultResponse())
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() => expect(screen.getByText('✓ Reported to Engineering')).toBeInTheDocument())

    const [runId, payload, key] = vi.mocked(hmiApi.reportFault).mock.calls[0]
    expect(runId).toBe(99)
    expect(payload).toEqual({
      reported_by: 'Liam',
      machine: 'BV1',
      reason: 'Film Jam',
      machine_id: 10,
      button_id: 20,
      note: null,
    })
    expect(key).toBeTruthy()
    // The fault is only shown as accepted once the backend confirms it.
    expect(
      screen.getByText(/fault 4 on bv1 is now with engineering \(not started\)/i),
    ).toBeInTheDocument()
  })

  it('requires a note when the machine has no configured fault button', async () => {
    vi.mocked(hmiApi.reportFault).mockResolvedValue(faultResponse({ machine: 'Casepacker' }))
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), {
      target: { value: 'Casepacker' },
    })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: 'Blockage' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/add a note/i)
    expect(hmiApi.reportFault).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/note \(required\)/i), {
      target: { value: 'Blocked at the infeed' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() => expect(hmiApi.reportFault).toHaveBeenCalledTimes(1))
    expect(vi.mocked(hmiApi.reportFault).mock.calls[0][1].note).toBe('Blocked at the infeed')
  })

  it('requires a machine and a reason', async () => {
    await openReportScreen()

    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/select a machine/i)
    expect(hmiApi.reportFault).not.toHaveBeenCalled()
  })

  it('one tap creates one fault even when tapped repeatedly', async () => {
    let resolve: (value: FaultReportResponse) => void = () => {}
    vi.mocked(hmiApi.reportFault).mockReturnValue(
      new Promise<FaultReportResponse>((r) => {
        resolve = r
      }),
    )
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: '20' } })
    const button = screen.getByRole('button', { name: /^report to engineer$/i })
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    expect(hmiApi.reportFault).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolve(faultResponse())
      await Promise.resolve()
    })
  })

  it('a retry after a failure reuses the same key and keeps the entered details', async () => {
    vi.mocked(hmiApi.reportFault).mockRejectedValueOnce(new ApiRequestError(503, 'down'))
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() => expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument())
    expect(screen.getByLabelText(/machine or section/i)).toHaveValue('BV1')

    vi.mocked(hmiApi.reportFault).mockResolvedValueOnce(faultResponse())
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() => expect(screen.getByText('✓ Reported to Engineering')).toBeInTheDocument())
    const calls = vi.mocked(hmiApi.reportFault).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0][2]).toBe(calls[1][2])
  })

  it('returns to the active run after confirmation', async () => {
    vi.mocked(hmiApi.reportFault).mockResolvedValue(faultResponse())
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() => expect(screen.getByText('✓ Reported to Engineering')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /back to active run/i }))

    expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument()
  })

  it('shows a safe message when the machine is rejected by the backend', async () => {
    vi.mocked(hmiApi.reportFault).mockRejectedValue(
      new ApiRequestError(422, 'That machine is not an active machine on this production line.'),
    )
    await openReportScreen()

    fireEvent.change(screen.getByLabelText(/machine or section/i), { target: { value: 'BV1' } })
    fireEvent.change(screen.getByLabelText(/fault reason/i), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: /^report to engineer$/i }))

    await waitFor(() =>
      expect(screen.getByText(/not an active machine on this production line/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText('✓ Reported to Engineering')).not.toBeInTheDocument()
  })
})
