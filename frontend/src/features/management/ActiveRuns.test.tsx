import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../routes/AppRoutes'
import { ApiRequestError, apiClient } from '../../api/client'
import * as managementApi from './api'
import type { ActiveRun, ForceCloseResponse } from './types'

vi.mock('./api')
vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>()
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: vi.fn(() => new Promise(() => {})) },
  }
})

const LOGIN = {
  status: 'success',
  token: 'runs-token',
  manager_name: 'Kuri',
  expires_at: '2099-01-01T00:00:00+00:00',
}

function activeRun(overrides: Partial<ActiveRun> = {}): ActiveRun {
  return {
    id: 42,
    production_line: 'GIC',
    line_technician: 'Marina',
    shift: 'Night',
    customer: 'Customer A',
    product: 'Product A',
    status: 'Active',
    started_at: '2026-09-28T21:10:00+00:00',
    // 1 day 3 h 25 min
    active_seconds: (27 * 60 + 25) * 60,
    last_hourly_update_at: '2026-09-28T23:00:00+00:00',
    hourly_update_count: 2,
    open_planned_stop_reason: null,
    open_planned_stop_started_at: null,
    open_changeover_id: null,
    open_line_fault_count: 3,
    ...overrides,
  }
}

const CLOSED: ForceCloseResponse = {
  status: 'success',
  run_id: 42,
  production_line: 'GIC',
  run_status: 'Cancelled',
  finished_at: '2026-09-30T00:35:00+00:00',
  closed_by: 'Kuri',
  reason: 'Tablet or browser closed',
  ended_planned_stop: null,
}

beforeEach(() => {
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
  vi.mocked(managementApi.getActiveRuns).mockResolvedValue({ items: [activeRun()] })
})

afterEach(() => {
  cleanup()
  vi.mocked(managementApi.login).mockReset()
  vi.mocked(managementApi.logout).mockReset()
  vi.mocked(managementApi.getActiveRuns).mockReset()
  vi.mocked(managementApi.forceCloseRun).mockReset()
  vi.mocked(apiClient.get).mockClear()
})

async function openActiveRuns() {
  vi.mocked(managementApi.login).mockResolvedValue(LOGIN)
  render(
    <MemoryRouter initialEntries={['/management/active-runs']}>
      <AppRoutes />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
  fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
  await screen.findByRole('heading', { level: 1, name: 'Active runs' })
}

function startForceClose() {
  fireEvent.click(screen.getByRole('button', { name: 'Force close the run on GIC' }))
}

describe('Active runs - access and list', () => {
  it('requires a Management session and reads nothing while signed out', () => {
    render(
      <MemoryRouter initialEntries={['/management/active-runs']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(screen.getByText(/sign in to open active runs/i)).toBeInTheDocument()
    expect(managementApi.getActiveRuns).not.toHaveBeenCalled()
  })

  it('shows line, technician, start time, how long it has run and what is open on the line', async () => {
    await openActiveRuns()

    const row = await screen.findByRole('row', { name: /GIC/ })
    expect(within(row).getByRole('rowheader')).toHaveTextContent('GIC')
    expect(row).toHaveTextContent('Marina')
    expect(row).toHaveTextContent('Mon 28 Sept, 22:10')
    expect(row).toHaveTextContent('1 d 3 h')
    expect(row).toHaveTextContent('3 open faults')
    expect(managementApi.getActiveRuns).toHaveBeenCalledWith('runs-token', expect.any(AbortSignal))
  })

  it('says plainly when no run is active', async () => {
    vi.mocked(managementApi.getActiveRuns).mockResolvedValue({ items: [] })
    await openActiveRuns()

    expect(await screen.findByText('No runs are active on any line.')).toBeInTheDocument()
  })

  it('is reachable from the Management home', async () => {
    vi.mocked(managementApi.login).mockResolvedValue(LOGIN)
    render(
      <MemoryRouter initialEntries={['/management']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
    fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    fireEvent.click(await screen.findByRole('link', { name: /active runs/i }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Active runs' })).toBeInTheDocument()
  })
})

describe('Active runs - force close', () => {
  it('requires a reason before the confirmation, and a note for Other', async () => {
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose why this run is being closed.')

    fireEvent.click(screen.getByRole('radio', { name: 'Other' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Write a note explaining the reason.')
    expect(managementApi.forceCloseRun).not.toHaveBeenCalled()
  })

  it('explains the consequences, then closes only on confirmation', async () => {
    vi.mocked(managementApi.forceCloseRun).mockResolvedValue(CLOSED)
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()

    fireEvent.click(screen.getByRole('radio', { name: 'Tablet or browser closed' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    const consequences = screen.getByRole('list', { name: 'What force-closing does' })
    expect(consequences).toHaveTextContent('marked Cancelled')
    expect(consequences).toHaveTextContent('Nothing is added for hours nobody reported (2 hours were reported)')
    expect(consequences).toHaveTextContent('The 3 open faults on GIC stay open')
    expect(consequences).toHaveTextContent('next technician must acknowledge them')
    expect(consequences).toHaveTextContent('then needs its next step recorded')
    expect(consequences).toHaveTextContent('management audit log')
    expect(managementApi.forceCloseRun).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Force close run on GIC' }))

    await waitFor(() =>
      expect(managementApi.forceCloseRun).toHaveBeenCalledWith('runs-token', 42, {
        reason: 'Tablet or browser closed',
        note: null,
      }),
    )
    const notice = await screen.findByText(/Run 42 on GIC was force-closed/)
    const region = notice.closest('[role="status"]') as HTMLElement
    expect(within(region).getByRole('link', { name: 'Production dashboard' })).toHaveAttribute('href', '/dashboard')
    // The list is read again so the closed run disappears.
    await waitFor(() => expect(managementApi.getActiveRuns).toHaveBeenCalledTimes(2))
  })

  it('says an open planned stop will be ended with the run', async () => {
    vi.mocked(managementApi.getActiveRuns).mockResolvedValue({
      items: [
        activeRun({
          open_planned_stop_reason: 'Break',
          open_planned_stop_started_at: '2026-09-28T23:30:00+00:00',
          open_line_fault_count: 0,
        }),
      ],
    })
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()
    fireEvent.click(screen.getByRole('radio', { name: 'Technician left mid-shift' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    const consequences = screen.getByRole('list', { name: 'What force-closing does' })
    expect(consequences).toHaveTextContent('The open planned stop “Break”')
    expect(consequences).toHaveTextContent('is ended at the same time')
    expect(consequences).toHaveTextContent('There are no open faults on GIC')
  })

  it('does not offer a force close while a changeover is open', async () => {
    vi.mocked(managementApi.getActiveRuns).mockResolvedValue({ items: [activeRun({ open_changeover_id: 7 })] })
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()

    expect(screen.getByRole('alert')).toHaveTextContent('Complete it on the GIC tablet (Changeover Complete) first')
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })

  it('shows the server refusal and changes nothing when the run was already closed', async () => {
    vi.mocked(managementApi.forceCloseRun).mockRejectedValue(
      new ApiRequestError(409, 'Production Run 42 was already closed by someone else.'),
    )
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()
    fireEvent.click(screen.getByRole('radio', { name: 'Duplicate run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Force close run on GIC' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already closed by someone else')
    expect(screen.queryByText(/was force-closed/)).not.toBeInTheDocument()
  })

  it('sends the manager back to sign in when the session has expired', async () => {
    vi.mocked(managementApi.forceCloseRun).mockRejectedValue(new ApiRequestError(401, 'expired'))
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()
    fireEvent.click(screen.getByRole('radio', { name: 'Production stopped' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Force close run on GIC' }))

    expect(await screen.findByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
  })

  it.each([0, 500, 503])('does not claim a force-close failed when the response is uncertain (%s)', async (status) => {
    vi.mocked(managementApi.forceCloseRun).mockRejectedValue(new ApiRequestError(status, 'unavailable'))
    await openActiveRuns()
    await screen.findByRole('row', { name: /GIC/ })
    startForceClose()
    fireEvent.click(screen.getByRole('radio', { name: 'Production stopped' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Force close run on GIC' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not confirm whether the run was closed')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Nothing was changed')
  })
})
