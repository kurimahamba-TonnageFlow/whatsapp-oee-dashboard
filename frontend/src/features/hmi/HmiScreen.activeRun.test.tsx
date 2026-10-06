import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { ApiRequestError } from '../../api/client'
import { saveActiveRun } from './activeRunStorage'
import { HMI_CONFIG, HOURS_ONE_DUE, changeover, plannedDowntimeEvent, runState } from './hmiTestState'
import type { HourlyUpdateResponse } from './types'

vi.mock('./api')

const MOCKED = [
  'getHmiConfig',
  'getRunState',
  'submitHourlyUpdate',
  'reviewHourlyLoss',
  'startPlannedDowntime',
  'endPlannedDowntime',
  'completeRun',
  'startRun',
] as const

afterEach(() => {
  // Scoped to this file's own mocks only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  MOCKED.forEach((name) => vi.mocked(hmiApi[name]).mockReset())
  window.localStorage.clear()
})

beforeEach(() => {
  vi.mocked(hmiApi.reviewHourlyLoss).mockResolvedValue({ target_packs: 7200, remaining_gap_packs: 0, equivalent_minutes: 0, prompt_required: false })
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(HMI_CONFIG)
})

function hourlyResponse(overrides: Partial<HourlyUpdateResponse> = {}): HourlyUpdateResponse {
  return {
    status: 'success',
    hourly_update_id: 77,
    production_run_id: 99,
    production_line: 'Rovema',
    hour_start: '2026-01-12T07:00:00+00:00',
    hour_label: '07:00–08:00',
    shift: 'Day',
    period_started_at: '2026-01-12T07:05:00+00:00',
    period_ended_at: '2026-01-12T08:05:00+00:00',
    period_minutes: 60,
    pallets_produced: 3.75,
    expected_packs: 7200,
    expected_pallets: 4.0909,
    expected_tonnes: 7.2,
    actual_packs: 6600,
    actual_tonnes: 6.6,
    output_gap_packs: 600,
    production_achievement_percent: 91.7,
    planned_downtime_minutes: 0,
    pallets_remaining: 30.5,
    total_pallets_completed: 7.5,
    potential_overrun_pallets: 0,
    ...overrides,
  }
}

function renderHmi() {
  return render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function renderActiveRun(state = runState()) {
  saveActiveRun({ runId: 99, productionLine: 'Rovema' })
  vi.mocked(hmiApi.getRunState).mockResolvedValue(state)

  const result = renderHmi()
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
  return result
}

// ==========================================================
// ACTIVE DOWNTIME DURATION
// ==========================================================

describe('Active downtime duration', () => {
  /** generated_at is "now", so nothing is added for time since refresh. */
  function freshlyGenerated(progress: Record<string, unknown>, extra = {}) {
    return runState({
      generated_at: new Date().toISOString(),
      progress: progress as never,
      ...extra,
    })
  }

  it('shows an active stop as its elapsed minutes, never as zero', async () => {
    await renderActiveRun(
      freshlyGenerated(
        {
          ...runState().progress,
          planned_downtime_minutes: 11,
          planned_downtime_completed_minutes: 0,
          planned_downtime_active_minutes: 11,
        },
        { open_planned_downtime: plannedDowntimeEvent({ elapsed_minutes: 11 }) },
      ),
    )

    expect(screen.getByText('Planned downtime (active now)')).toBeInTheDocument()
    expect(
      screen.getByText('Planned downtime (active now)').closest('div'),
    ).toHaveTextContent('11 min')
    // The banner names the elapsed time too, not just the start time.
    expect(screen.getByText(/running for/i)).toBeInTheDocument()
  })

  it('separates completed downtime from the stop currently running', async () => {
    await renderActiveRun(
      freshlyGenerated(
        {
          ...runState().progress,
          planned_downtime_minutes: 26,
          planned_downtime_completed_minutes: 15,
          planned_downtime_active_minutes: 11,
        },
        { open_planned_downtime: plannedDowntimeEvent({ elapsed_minutes: 11 }) },
      ),
    )

    expect(
      screen.getByText('Planned downtime (completed)').closest('div'),
    ).toHaveTextContent('15 min')
    expect(
      screen.getByText('Planned downtime (active now)').closest('div'),
    ).toHaveTextContent('11 min')
    // The merged server total, not completed + active added blindly.
    expect(screen.getByText('Planned downtime to date').closest('div')).toHaveTextContent('26 min')
  })

  it('shows completed downtime with no active row when nothing is stopped', async () => {
    await renderActiveRun(
      freshlyGenerated({
        ...runState().progress,
        planned_downtime_minutes: 15,
        planned_downtime_completed_minutes: 15,
        planned_downtime_active_minutes: null,
      }),
    )

    expect(screen.getByText('Planned downtime (completed)')).toBeInTheDocument()
    expect(screen.queryByText('Planned downtime (active now)')).not.toBeInTheDocument()
    expect(screen.getByText('Planned downtime to date').closest('div')).toHaveTextContent('15 min')
  })

  it('shows an active changeover duration as well as the stop', async () => {
    await renderActiveRun(
      freshlyGenerated(
        {
          ...runState().progress,
          planned_downtime_minutes: 12,
          planned_downtime_completed_minutes: 0,
          planned_downtime_active_minutes: 12,
          changeover_active_minutes: 12,
        },
        {
          open_planned_downtime: plannedDowntimeEvent({
            reason: 'Changeover',
            elapsed_minutes: 12,
          }),
          open_changeover: changeover(),
        },
      ),
    )

    expect(screen.getByText('Changeover (active now)')).toBeInTheDocument()
    expect(screen.getByText('Changeover (active now)').closest('div')).toHaveTextContent('12 min')
  })

  it('takes the backend figure as authoritative on refresh', async () => {
    await renderActiveRun(
      freshlyGenerated(
        {
          ...runState().progress,
          planned_downtime_minutes: 11,
          planned_downtime_completed_minutes: 0,
          planned_downtime_active_minutes: 11,
        },
        { open_planned_downtime: plannedDowntimeEvent({ elapsed_minutes: 11 }) },
      ),
    )
    expect(
      screen.getByText('Planned downtime (active now)').closest('div'),
    ).toHaveTextContent('11 min')

    vi.mocked(hmiApi.getRunState).mockResolvedValue(
      freshlyGenerated(
        {
          ...runState().progress,
          planned_downtime_minutes: 19,
          planned_downtime_completed_minutes: 0,
          planned_downtime_active_minutes: 19,
        },
        { open_planned_downtime: plannedDowntimeEvent({ elapsed_minutes: 19 }) },
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))

    await waitFor(() =>
      expect(
        screen.getByText('Planned downtime (active now)').closest('div'),
      ).toHaveTextContent('19 min'),
    )
  })
})

// ==========================================================
// RECOVERY
// ==========================================================

describe('Active-run recovery', () => {
  it('restores the run from the backend, not from local state', async () => {
    await renderActiveRun()

    expect(hmiApi.getRunState).toHaveBeenCalledWith(99)
    expect(screen.getByText('Liam')).toBeInTheDocument()
    expect(screen.getByText('Days')).toBeInTheDocument()
    expect(screen.getByText('3.75')).toBeInTheDocument() // pallets completed
    expect(screen.getByText('34.25')).toBeInTheDocument() // pallets remaining
    expect(screen.getByText('6600 packs')).toBeInTheDocument() // actual output
  })

  it('restores an open planned downtime', async () => {
    await renderActiveRun(
      runState({ open_planned_downtime: plannedDowntimeEvent({ reason: 'CCP Check' }) }),
    )

    expect(screen.getByText(/planned downtime in progress: ccp check/i)).toBeInTheDocument()
  })

  it('restores an open changeover', async () => {
    await renderActiveRun(runState({ open_changeover: changeover() }))

    expect(screen.getByText(/changeover in progress to tesco/i)).toBeInTheDocument()
  })

  it('shows a safe recovery error when the backend cannot be reached, and never starts a run', async () => {
    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState).mockRejectedValue(new ApiRequestError(503, 'unavailable'))

    renderHmi()

    await waitFor(() =>
      expect(
        screen.getByText(/could not reach pulse to restore the active run/i),
      ).toBeInTheDocument(),
    )
    expect(hmiApi.startRun).not.toHaveBeenCalled()
    expect(window.localStorage.getItem('pulse.hmi.activeRun.v2')).not.toBeNull()
  })

  it('clears a run the backend no longer has', async () => {
    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState).mockRejectedValue(new ApiRequestError(404, 'not found'))

    renderHmi()

    await waitFor(() => expect(screen.getByText(/that run no longer exists/i)).toBeInTheDocument())
    expect(window.localStorage.getItem('pulse.hmi.activeRun.v2')).toBeNull()
  })

  it('shows the hourly update prompt once it is due', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-12T08:11:00Z'))
    try {
      saveActiveRun({ runId: 99, productionLine: 'Rovema' })
      vi.mocked(hmiApi.getRunState).mockResolvedValue(runState({ hours: HOURS_ONE_DUE }))

      renderHmi()
      await act(async () => {
        await Promise.resolve()
      })

      expect(screen.getByText('Hourly update due: 07:00–08:00')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})

// ==========================================================
// HOURLY UPDATE
// ==========================================================

describe('Hourly Update', () => {
  it('asks about residual loss and can record an unknown cause without inventing a reason', async () => {
    vi.mocked(hmiApi.reviewHourlyLoss).mockResolvedValue({ target_packs: 6000, remaining_gap_packs: 2800, equivalent_minutes: 28, prompt_required: true })
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())
    const input = await openHourlyUpdate()
    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00/i }))
    await screen.findByText('28 minutes')
    expect(hmiApi.submitHourlyUpdate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /cause unknown/i }))
    await waitFor(() => expect(hmiApi.submitHourlyUpdate).toHaveBeenCalledTimes(1))
    expect(vi.mocked(hmiApi.submitHourlyUpdate).mock.calls[0][1].other_loss_reason).toBeUndefined()
  })

  it('does not submit a reading when the loss review is unavailable', async () => {
    vi.mocked(hmiApi.reviewHourlyLoss).mockRejectedValue(new Error('unavailable'))
    const input = await openHourlyUpdate()
    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00/i }))
    await screen.findByText(/could not check the output gap/i)
    expect(hmiApi.submitHourlyUpdate).not.toHaveBeenCalled()
  })
  async function openHourlyUpdate(state = runState({ hours: HOURS_ONE_DUE })) {
    await renderActiveRun(state)
    fireEvent.click(screen.getByRole('button', { name: /report hour/i }))
    return screen.getByLabelText(/pallets produced 07:00–08:00/i)
  }

  it('submits a decimal value as an exact string and shows the confirmed backend figures', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '3.75' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(screen.getByText('✓ 07:00–08:00 recorded')).toBeInTheDocument())

    const [runId, payload, key] = vi.mocked(hmiApi.submitHourlyUpdate).mock.calls[0]
    expect(runId).toBe(99)
    expect(payload).toEqual({
      line_technician: 'Liam',
      hour_start: '2026-01-12T07:00:00+00:00',
      pallets_produced: '3.75',
    })
    expect(key).toMatch(/^k-[A-Za-z0-9_-]{14,}$/)
    expect(screen.getAllByText('91.7%')).toHaveLength(2)
  })

  it('accepts zero pallets', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(
      hourlyResponse({ pallets_produced: 0, total_pallets_completed: 3.75 }),
    )
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(screen.getByText('✓ 07:00–08:00 recorded')).toBeInTheDocument())
    expect(vi.mocked(hmiApi.submitHourlyUpdate).mock.calls[0][1].pallets_produced).toBe('0')
  })

  it('saves an hourly loss explanation even when a planned stop exists', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())
    const input = await openHourlyUpdate(runState({ hours: HOURS_ONE_DUE, open_planned_downtime: plannedDowntimeEvent() }))
    fireEvent.change(input, { target: { value: '1.25' } })
    fireEvent.change(screen.getByLabelText(/other output loss this hour/i), {
      target: { value: '  Slow feeding after the film change  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))
    await waitFor(() => expect(hmiApi.submitHourlyUpdate).toHaveBeenCalledTimes(1))
    expect(vi.mocked(hmiApi.submitHourlyUpdate).mock.calls[0][1]).toMatchObject({
      pallets_produced: '1.25', other_loss_reason: 'Slow feeding after the film change',
    })
  })

  it.each(['-1', 'abc', '1.23456', ''])('rejects %s without calling the API', async (value) => {
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hmiApi.submitHourlyUpdate).not.toHaveBeenCalled()
  })

  it('a double tap sends exactly one request', async () => {
    let resolve: (value: HourlyUpdateResponse) => void = () => {}
    vi.mocked(hmiApi.submitHourlyUpdate).mockReturnValue(
      new Promise<HourlyUpdateResponse>((r) => {
        resolve = r
      }),
    )
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '2' } })
    const confirm = screen.getByRole('button', { name: /save 07:00–08:00/i })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    await waitFor(() => expect(hmiApi.submitHourlyUpdate).toHaveBeenCalledTimes(1))

    await act(async () => {
      resolve(hourlyResponse())
      await Promise.resolve()
    })
  })

  it('a retry after a failure reuses the same idempotency key and keeps the entered value', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockRejectedValueOnce(new ApiRequestError(503, 'down'))
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '3.75' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(screen.getByText(/may already have saved/i)).toBeInTheDocument())
    expect(screen.getByLabelText(/pallets produced 07:00–08:00/i)).toHaveValue('3.75')

    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValueOnce(hourlyResponse())
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(screen.getByText('✓ 07:00–08:00 recorded')).toBeInTheDocument())
    const calls = vi.mocked(hmiApi.submitHourlyUpdate).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0][2]).toBe(calls[1][2])
  })

  it('two different updates use different keys', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))
    await waitFor(() => expect(screen.getByText('✓ 07:00–08:00 recorded')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /back to the run|next missed hour/i }))
    fireEvent.change(screen.getByLabelText(/pallets produced 07:00–08:00/i), {
      target: { value: '1' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(hmiApi.submitHourlyUpdate).toHaveBeenCalledTimes(2))
    const calls = vi.mocked(hmiApi.submitHourlyUpdate).mock.calls
    expect(calls[0][2]).not.toBe(calls[1][2])
  })

  it('refreshes the run from the server after a confirmed update', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())
    const updated = runState()
    updated.run.total_pallets_completed = 7.5
    updated.run.pallets_remaining = 30.5

    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState)
      .mockResolvedValueOnce(runState({ hours: HOURS_ONE_DUE }))
      .mockResolvedValue(updated)

    renderHmi()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /report hour/i }))
    fireEvent.change(screen.getByLabelText(/pallets produced 07:00–08:00/i), {
      target: { value: '3.75' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() => expect(hmiApi.getRunState).toHaveBeenCalledTimes(2))
    fireEvent.click(await screen.findByRole('button', { name: /back to the run/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
    expect(screen.getByText('7.5')).toBeInTheDocument()
  })

  it('an unconfirmed update is offered for retry after a reload, with the same key', async () => {
    window.localStorage.setItem(
      'pulse.hmi.pendingAction.v1',
      JSON.stringify({
        kind: 'hourlyUpdate',
        key: 'k-pending-0000000000000001',
        runId: 99,
        label: '3.75 pallets for 07:00–08:00',
        payload: { hourStart: '2026-01-12T07:00:00+00:00', palletsProduced: '3.75', lossReason: 'Material shortage' },
        createdAtIso: '2026-01-12T08:00:00.000Z',
      }),
    )
    vi.mocked(hmiApi.submitHourlyUpdate).mockResolvedValue(hourlyResponse())

    await renderActiveRun(runState({ hours: HOURS_ONE_DUE }))

    expect(
      screen.getByText(/3.75 pallets for 07:00–08:00 was not confirmed/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /check and retry/i }))
    await waitFor(() => expect(hmiApi.submitHourlyUpdate).toHaveBeenCalled())
    expect(hmiApi.submitHourlyUpdate).toHaveBeenCalledWith(99, {
      line_technician: 'Liam', hour_start: '2026-01-12T07:00:00+00:00', pallets_produced: '3.75', other_loss_reason: 'Material shortage',
    }, 'k-pending-0000000000000001')
  })

  it('a conflict from the server is shown as a safe message', async () => {
    vi.mocked(hmiApi.submitHourlyUpdate).mockRejectedValue(
      new ApiRequestError(409, 'This request was already used with different details.'),
    )
    const input = await openHourlyUpdate()

    fireEvent.change(input, { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /save 07:00–08:00/i }))

    await waitFor(() =>
      expect(screen.getByText(/already used with different details/i)).toBeInTheDocument(),
    )
  })
})

// ==========================================================
// PLANNED DOWNTIME
// ==========================================================

describe('Planned Downtime', () => {
  it('starts a planned stop and shows it as active from the refreshed server state', async () => {
    vi.mocked(hmiApi.startPlannedDowntime).mockResolvedValue({
      status: 'success',
      ...plannedDowntimeEvent(),
    })
    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState)
      .mockResolvedValueOnce(runState())
      .mockResolvedValue(runState({ open_planned_downtime: plannedDowntimeEvent() }))

    renderHmi()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Label Change' }))

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /planned downtime — label change/i }),
      ).toBeInTheDocument(),
    )
    const [runId, payload, key] = vi.mocked(hmiApi.startPlannedDowntime).mock.calls[0]
    expect(runId).toBe(99)
    expect(payload).toEqual({ reason: 'Label Change', started_by: 'Liam' })
    expect(key).toBeTruthy()
    expect(screen.getByText(/elapsed:/i)).toBeInTheDocument()
  })

  it('ends the planned stop and returns to the active run', async () => {
    vi.mocked(hmiApi.endPlannedDowntime).mockResolvedValue({
      status: 'success',
      ...plannedDowntimeEvent({ ended_at: '2026-01-12T07:45:00+00:00', duration_minutes: 15 }),
    })
    const ended = runState()
    ended.progress.planned_downtime_minutes = 15

    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState)
      .mockResolvedValueOnce(runState({ open_planned_downtime: plannedDowntimeEvent() }))
      .mockResolvedValue(ended)

    renderHmi()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: /end planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: /yes, end downtime/i }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
    expect(vi.mocked(hmiApi.endPlannedDowntime).mock.calls[0][0]).toBe(31)
    expect(screen.getByText('15 min')).toBeInTheDocument()
  })

  it('a double tap starts only one planned stop', async () => {
    let resolve: (value: never) => void = () => {}
    vi.mocked(hmiApi.startPlannedDowntime).mockReturnValue(
      new Promise((r) => {
        resolve = r as never
      }),
    )

    await renderActiveRun()
    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    const button = screen.getByRole('button', { name: 'Film Change' })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(hmiApi.startPlannedDowntime).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolve({ status: 'success', ...plannedDowntimeEvent() } as never)
      await Promise.resolve()
    })
  })

  it('a server conflict is shown without claiming downtime started', async () => {
    vi.mocked(hmiApi.startPlannedDowntime).mockRejectedValue(
      new ApiRequestError(409, 'Planned downtime is already in progress for this run.'),
    )

    await renderActiveRun()
    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: 'CCP Check' }))

    await waitFor(() =>
      expect(screen.getByText(/already in progress for this run/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'Planned Downtime' })).toBeInTheDocument()
  })

  it('a server failure while ending keeps the stop shown as active', async () => {
    vi.mocked(hmiApi.endPlannedDowntime).mockRejectedValue(new ApiRequestError(503, 'down'))

    await renderActiveRun(runState({ open_planned_downtime: plannedDowntimeEvent() }))
    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: /end planned downtime/i }))
    fireEvent.click(screen.getByRole('button', { name: /yes, end downtime/i }))

    await waitFor(() => expect(screen.getByText(/may already have saved/i)).toBeInTheDocument())
    expect(
      screen.getByRole('heading', { name: /planned downtime — label change/i }),
    ).toBeInTheDocument()
  })

  it('Changeover is not offered as a plain planned-downtime reason', async () => {
    await renderActiveRun()
    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))

    expect(screen.queryByRole('button', { name: /^Changeover$/ })).not.toBeInTheDocument()
    // A product change is End Run -> Changeover, never an in-run stop.
    expect(screen.queryByRole('button', { name: /start changeover/i })).not.toBeInTheDocument()
    expect(screen.getByText(/use end run, then choose changeover/i)).toBeInTheDocument()
  })
})

// ==========================================================
// EXIT
// ==========================================================

describe('Exit or Restart', () => {
  it('clears this device only and never completes the run', async () => {
    await renderActiveRun()

    fireEvent.click(screen.getByRole('button', { name: /exit or restart run/i }))
    expect(screen.getByText(/this run will stay active in the system/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /exit to home/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /select a production line/i })).toBeInTheDocument(),
    )
    expect(hmiApi.completeRun).not.toHaveBeenCalled()
    expect(window.localStorage.getItem('pulse.hmi.activeRun.v2')).toBeNull()
  })
})
