import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { ApiRequestError } from '../../api/client'
import { saveActiveRun } from './activeRunStorage'
import { HMI_CONFIG, changeover, plannedDowntimeEvent, runState } from './hmiTestState'
import type { ChangeoverPairResponse } from './types'

vi.mock('./api')

const MOCKED = [
  'getHmiConfig',
  'getRunState',
  'startChangeover',
  'completeChangeover',
  'startPlannedDowntime',
  'endPlannedDowntime',
] as const

afterEach(() => {
  MOCKED.forEach((name) => vi.mocked(hmiApi[name]).mockReset())
  window.localStorage.clear()
})

beforeEach(() => {
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(HMI_CONFIG)
})

function pairResponse(): ChangeoverPairResponse {
  return {
    status: 'success',
    changeover: changeover(),
    planned_downtime: plannedDowntimeEvent({ reason: 'Changeover' }),
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
  renderHmi()
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
}

async function openChangeoverForm() {
  await renderActiveRun()
  fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
  fireEvent.click(screen.getByRole('button', { name: /start changeover/i }))
}

function fillChangeoverForm() {
  fireEvent.change(screen.getByLabelText(/new customer/i), { target: { value: 'Tesco' } })
  fireEvent.change(screen.getByLabelText(/new product or rice type/i), {
    target: { value: 'Jasmine' },
  })
  fireEvent.change(screen.getByLabelText(/new pack weight/i), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText(/new format/i), { target: { value: 'Block bottom' } })
}

describe('Start Changeover', () => {
  it('shows the current run as the previous configuration', async () => {
    await openChangeoverForm()

    expect(screen.getByRole('heading', { name: /start changeover/i })).toBeInTheDocument()
    expect(screen.getByText('Asda')).toBeInTheDocument()
    expect(screen.getByText('White Basmati')).toBeInTheDocument()
    expect(screen.getByText('1 kg')).toBeInTheDocument()
    expect(screen.getByText('Pillow')).toBeInTheDocument()
  })

  it('starts the planned stop and the changeover record in one request', async () => {
    vi.mocked(hmiApi.startChangeover).mockResolvedValue(pairResponse())
    await openChangeoverForm()

    fillChangeoverForm()
    fireEvent.click(screen.getByRole('button', { name: /^start changeover$/i }))

    await waitFor(() => expect(hmiApi.startChangeover).toHaveBeenCalledTimes(1))
    const [runId, payload, key] = vi.mocked(hmiApi.startChangeover).mock.calls[0]
    expect(runId).toBe(99)
    expect(payload).toEqual({
      line_technician: 'Liam',
      new_customer: 'Tesco',
      new_product: 'Jasmine',
      new_pack_weight_kg: '4',
      new_format: 'Block bottom',
      note: null,
    })
    expect(key).toBeTruthy()
    // One user action, one request - the planned stop is not started separately.
    expect(hmiApi.startPlannedDowntime).not.toHaveBeenCalled()
  })

  it.each([
    ['new customer', /new customer/i],
    ['new product', /new product or rice type/i],
    ['new pack weight', /new pack weight/i],
    ['new format', /new format/i],
  ])('requires the %s', async (_label, matcher) => {
    await openChangeoverForm()
    fillChangeoverForm()
    fireEvent.change(screen.getByLabelText(matcher), { target: { value: '   ' } })

    fireEvent.click(screen.getByRole('button', { name: /^start changeover$/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hmiApi.startChangeover).not.toHaveBeenCalled()
  })

  it('rejects a zero pack weight', async () => {
    await openChangeoverForm()
    fillChangeoverForm()
    fireEvent.change(screen.getByLabelText(/new pack weight/i), { target: { value: '0' } })

    fireEvent.click(screen.getByRole('button', { name: /^start changeover$/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hmiApi.startChangeover).not.toHaveBeenCalled()
  })

  it('a double tap starts only one changeover', async () => {
    let resolve: (value: ChangeoverPairResponse) => void = () => {}
    vi.mocked(hmiApi.startChangeover).mockReturnValue(
      new Promise<ChangeoverPairResponse>((r) => {
        resolve = r
      }),
    )
    await openChangeoverForm()
    fillChangeoverForm()

    const button = screen.getByRole('button', { name: /^start changeover$/i })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(hmiApi.startChangeover).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolve(pairResponse())
      await Promise.resolve()
    })
  })

  it('keeps the entered configuration when the request fails', async () => {
    vi.mocked(hmiApi.startChangeover).mockRejectedValue(new ApiRequestError(503, 'down'))
    await openChangeoverForm()
    fillChangeoverForm()

    fireEvent.click(screen.getByRole('button', { name: /^start changeover$/i }))

    await waitFor(() => expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument())
    expect(screen.getByLabelText(/new customer/i)).toHaveValue('Tesco')
    expect(screen.getByLabelText(/new format/i)).toHaveValue('Block bottom')
  })

  it('shows a conflict when the line already has an open changeover', async () => {
    vi.mocked(hmiApi.startChangeover).mockRejectedValue(
      new ApiRequestError(409, "Production Line 'Rovema' already has an open changeover."),
    )
    await openChangeoverForm()
    fillChangeoverForm()

    fireEvent.click(screen.getByRole('button', { name: /^start changeover$/i }))

    await waitFor(() =>
      expect(screen.getByText(/already has an open changeover/i)).toBeInTheDocument(),
    )
  })
})

describe('Changeover Complete', () => {
  async function openOpenChangeover() {
    await renderActiveRun(
      runState({
        open_changeover: changeover(),
        open_planned_downtime: plannedDowntimeEvent({ reason: 'Changeover' }),
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
  }

  it('shows the previous and new configuration', async () => {
    await openOpenChangeover()

    expect(screen.getByRole('heading', { name: /changeover in progress/i })).toBeInTheDocument()
    expect(screen.getByText(/asda — white basmati/i)).toBeInTheDocument()
    expect(screen.getByText(/tesco — jasmine/i)).toBeInTheDocument()
    expect(screen.getByText('4 kg')).toBeInTheDocument()
  })

  it('cannot be completed until first acceptable packs are confirmed', async () => {
    await openOpenChangeover()

    expect(screen.getByRole('button', { name: /changeover complete/i })).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/first acceptable packs of the new run/i))

    expect(screen.getByRole('button', { name: /changeover complete/i })).toBeEnabled()
    expect(hmiApi.completeChangeover).not.toHaveBeenCalled()
  })

  it('completes the changeover and its planned stop together', async () => {
    vi.mocked(hmiApi.completeChangeover).mockResolvedValue({
      status: 'success',
      changeover: changeover({ status: 'Completed', duration_minutes: 42.5 }),
      planned_downtime: plannedDowntimeEvent({ reason: 'Changeover', duration_minutes: 42.5 }),
    })
    saveActiveRun({ runId: 99, productionLine: 'Rovema' })
    vi.mocked(hmiApi.getRunState)
      .mockResolvedValueOnce(
        runState({
          open_changeover: changeover(),
          open_planned_downtime: plannedDowntimeEvent({ reason: 'Changeover' }),
        }),
      )
      .mockResolvedValue(runState())

    renderHmi()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /planned downtime/i }))
    fireEvent.click(screen.getByLabelText(/first acceptable packs of the new run/i))
    fireEvent.click(screen.getByRole('button', { name: /changeover complete/i }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
    const [changeoverId, payload] = vi.mocked(hmiApi.completeChangeover).mock.calls[0]
    expect(changeoverId).toBe(6)
    expect(payload).toEqual({ completed_by: 'Liam', first_acceptable_packs_confirmed: true })
    // The planned stop is never ended separately.
    expect(hmiApi.endPlannedDowntime).not.toHaveBeenCalled()
    expect(screen.queryByText(/changeover in progress to/i)).not.toBeInTheDocument()
  })

  it('a double tap completes it only once', async () => {
    let resolve: (value: ChangeoverPairResponse) => void = () => {}
    vi.mocked(hmiApi.completeChangeover).mockReturnValue(
      new Promise<ChangeoverPairResponse>((r) => {
        resolve = r
      }),
    )
    await openOpenChangeover()
    fireEvent.click(screen.getByLabelText(/first acceptable packs of the new run/i))

    const button = screen.getByRole('button', { name: /changeover complete/i })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(hmiApi.completeChangeover).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolve(pairResponse())
      await Promise.resolve()
    })
  })

  it('a failure leaves the changeover open and shows a safe message', async () => {
    vi.mocked(hmiApi.completeChangeover).mockRejectedValue(new ApiRequestError(503, 'down'))
    await openOpenChangeover()

    fireEvent.click(screen.getByLabelText(/first acceptable packs of the new run/i))
    fireEvent.click(screen.getByRole('button', { name: /changeover complete/i }))

    await waitFor(() => expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: /changeover in progress/i })).toBeInTheDocument()
  })

  it('an already-completed changeover reports a conflict', async () => {
    vi.mocked(hmiApi.completeChangeover).mockRejectedValue(
      new ApiRequestError(409, 'Changeover 6 is already completed.'),
    )
    await openOpenChangeover()

    fireEvent.click(screen.getByLabelText(/first acceptable packs of the new run/i))
    fireEvent.click(screen.getByRole('button', { name: /changeover complete/i }))

    await waitFor(() => expect(screen.getByText(/already completed/i)).toBeInTheDocument())
  })
})
