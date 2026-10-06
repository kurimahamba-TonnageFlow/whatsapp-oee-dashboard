import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../routes/AppRoutes'
import { ApiRequestError, apiClient } from '../../api/client'
import * as managementApi from '../management/api'
import * as dashboardApi from '../dashboard/api'
import * as performanceApi from './api'
import type { TechnicianPerformanceResponse, TechnicianResult } from './types'

vi.mock('../management/api')
vi.mock('../dashboard/api')
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
  token: 'perf-token',
  manager_name: 'Kuri',
  expires_at: '2099-01-01T00:00:00+00:00',
}

function result(name: string, overrides: Partial<TechnicianResult> = {}): TechnicianResult {
  return {
    line_technician: name,
    completed_runs: 5,
    expected_pallets: 100,
    actual_pallets: 96,
    expected_tonnes: 20,
    actual_tonnes: 19.2,
    output_gap_pallets: 4,
    output_gap_tonnes: 0.8,
    target_achievement_percent: 96,
    data_completion_rate_percent: 100,
    label: 'On target',
    lines: ['Rovema'],
    ...overrides,
  }
}

function response(overrides: Partial<TechnicianPerformanceResponse> = {}): TechnicianPerformanceResponse {
  return {
    period: 'current_month',
    date_from: '2026-09-01',
    date_to: '2026-09-30',
    minimum_sample_size: 3,
    ranked: [
      result('Alex'),
      result('Sam', {
        completed_runs: 4,
        expected_tonnes: 10,
        actual_tonnes: 8.456,
        output_gap_tonnes: 1.544,
        target_achievement_percent: 84.56,
        label: 'At risk',
      }),
      result('Jo', {
        completed_runs: 3,
        expected_tonnes: 0,
        actual_tonnes: 0,
        output_gap_tonnes: 0,
        target_achievement_percent: null,
        label: 'Insufficient data',
      }),
    ],
    insufficient_data: [result('Robin', { completed_runs: 1, label: 'Insufficient data' })],
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
  vi.mocked(performanceApi.getTechnicianPerformance).mockResolvedValue(response())
  vi.mocked(dashboardApi.getFilterOptions).mockResolvedValue({
    production_lines: ['GIC', 'Guill', 'Rovema'],
    shifts: ['Day', 'Night'],
    products: ['Product A'],
    customers: ['Customer A'],
    technicians: ['Alex', 'Sam'],
  })
})

afterEach(() => {
  cleanup()
  vi.mocked(managementApi.login).mockReset()
  vi.mocked(managementApi.logout).mockReset()
  vi.mocked(performanceApi.getTechnicianPerformance).mockReset()
  vi.mocked(dashboardApi.getFilterOptions).mockReset()
  vi.mocked(apiClient.get).mockClear()
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

async function openPerformance() {
  vi.mocked(managementApi.login).mockResolvedValue(LOGIN)
  renderAt('/management/performance')
  fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
  fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
  await screen.findByRole('heading', { level: 1, name: 'Line Technician Performance' })
}

function lastFilters() {
  return vi.mocked(performanceApi.getTechnicianPerformance).mock.lastCall?.[1]
}

describe('Technician performance - access and framing', () => {
  it('requires a Management session and reads nothing while signed out', () => {
    renderAt('/management/performance')

    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(screen.getByText(/sign in to open technician performance/i)).toBeInTheDocument()
    expect(performanceApi.getTechnicianPerformance).not.toHaveBeenCalled()
  })

  it('explains the comparison and warns against using figures alone for discipline', async () => {
    await openPerformance()

    expect(screen.getByText(/compare each technician's completed production runs against target/i)).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(/should not be used on their own for disciplinary decisions/i)
    // The read starts in an effect just after the page first renders.
    await waitFor(() => expect(performanceApi.getTechnicianPerformance).toHaveBeenCalled())
    expect(vi.mocked(performanceApi.getTechnicianPerformance).mock.calls[0][0]).toBe('perf-token')
  })
})

describe('Technician performance - leaderboard', () => {
  it('shows the required columns and ranks technicians in the backend order', async () => {
    await openPerformance()
    const table = within(await screen.findByRole('region', { name: 'Leaderboard table' })).getByRole('table')
    const rows = within(table).getAllByRole('row')

    expect(within(rows[0]).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Rank', 'Technician', 'Completed runs', 'Expected output', 'Actual output', 'Against target', 'Output gap',
    ])
    expect(within(rows[1]).getAllByRole('cell')[0]).toHaveTextContent('1')
    expect(within(rows[1]).getByRole('rowheader')).toHaveTextContent('Alex')
    expect(within(rows[1]).getByText('20.00 t')).toBeInTheDocument()
    expect(within(rows[1]).getByText('19.20 t')).toBeInTheDocument()
    expect(within(rows[1]).getByText(/96\.0%/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('0.80 t')).toBeInTheDocument()

    expect(within(rows[2]).getAllByRole('cell')[0]).toHaveTextContent('2')
    expect(within(rows[2]).getByText(/84\.6%/)).toBeInTheDocument()
    expect(within(rows[2]).getByText('At risk')).toBeInTheDocument()
  })

  it('never ranks a technician with no target data, and never shows it as 0%', async () => {
    await openPerformance()
    const table = within(await screen.findByRole('region', { name: 'Leaderboard table' })).getByRole('table')
    const jo = within(table).getByRole('rowheader', { name: 'Jo' }).closest('tr') as HTMLElement

    expect(within(jo).getAllByRole('cell')[0]).toHaveTextContent('—')
    expect(within(jo).getByText(/No target data/)).toBeInTheDocument()
    expect(within(jo).queryByText(/0\.0%/)).not.toBeInTheDocument()
  })

  it('lists technicians with too few runs as Insufficient data, separately and unranked', async () => {
    await openPerformance()
    const region = await screen.findByRole('region', { name: 'Insufficient data table' })

    expect(screen.getByRole('heading', { name: 'Not enough evidence to compare' })).toBeInTheDocument()
    expect(screen.getByText(/fewer than 3 completed runs in this period/i)).toBeInTheDocument()
    const robin = within(region).getByRole('rowheader', { name: 'Robin' }).closest('tr') as HTMLElement
    expect(within(robin).getByText('Insufficient data')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Leaderboard table' })).queryByText('Robin')).not.toBeInTheDocument()
  })

  it('uses the same neutral styling for every label - nothing is colour-coded as blame', async () => {
    await openPerformance()
    await screen.findByRole('region', { name: 'Leaderboard table' })

    for (const label of ['On target', 'At risk', 'Insufficient data']) {
      for (const chip of screen.getAllByText(label, { selector: '.pulse-status' })) {
        expect(chip).toHaveClass('pulse-status--neutral')
        expect(chip.className).not.toMatch(/red|amber|danger|warning/)
      }
    }
  })

  it('shows the resolved period dates and the minimum sample size', async () => {
    await openPerformance()

    expect(await screen.findByText(/1 Sept? 2026 to 30 Sept? 2026/)).toBeInTheDocument()
    expect(screen.getByText(/at least 3 completed runs/i)).toBeInTheDocument()
  })
})

describe('Technician performance - filters', () => {
  it('starts with this month and passes each supported filter to the API', async () => {
    await openPerformance()
    await waitFor(() => expect(lastFilters()?.period).toBe('current_month'))
    await screen.findByRole('option', { name: 'Night' })

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: 'previous_week' } })
    fireEvent.change(screen.getByLabelText('Line'), { target: { value: 'GIC' } })
    fireEvent.change(screen.getByLabelText('Shift'), { target: { value: 'Night' } })
    fireEvent.change(screen.getByLabelText('Technician'), { target: { value: 'Sam' } })
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'Product A' } })
    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: 'Customer A' } })

    await waitFor(() =>
      expect(lastFilters()).toMatchObject({
        period: 'previous_week',
        production_line: 'GIC',
        shift: 'Night',
        technician: 'Sam',
        product: 'Product A',
        customer: 'Customer A',
      }),
    )
  })

  it('needs both custom dates, in order, before asking the API', async () => {
    await openPerformance()
    await screen.findByRole('region', { name: 'Leaderboard table' })
    const callsBefore = vi.mocked(performanceApi.getTechnicianPerformance).mock.calls.length

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: 'custom' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose both a start date and an end date.')

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-20' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-09-10' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('The start date must be on or before the end date.')
    expect(vi.mocked(performanceApi.getTechnicianPerformance).mock.calls.length).toBe(callsBefore)

    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-09-25' } })
    await waitFor(() =>
      expect(lastFilters()).toMatchObject({ period: 'custom', date_from: '2026-09-20', date_to: '2026-09-25' }),
    )
  })
})

describe('Technician performance - states', () => {
  it('shows a loading state', async () => {
    vi.mocked(performanceApi.getTechnicianPerformance).mockReturnValue(new Promise(() => {}))
    await openPerformance()

    expect(screen.getByText('Loading technician results…')).toBeInTheDocument()
  })

  it('shows an empty state when no completed runs match', async () => {
    vi.mocked(performanceApi.getTechnicianPerformance).mockResolvedValue(
      response({ ranked: [], insufficient_data: [] }),
    )
    await openPerformance()

    expect(await screen.findByRole('heading', { name: 'No completed runs' })).toBeInTheDocument()
  })

  it('explains when everyone has too few runs to be ranked', async () => {
    vi.mocked(performanceApi.getTechnicianPerformance).mockResolvedValue(response({ ranked: [] }))
    await openPerformance()

    expect(
      await screen.findByText('No technician has enough completed runs in this period to be ranked yet.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Insufficient data table' })).toBeInTheDocument()
  })

  it('shows a safe error with Try again', async () => {
    vi.mocked(performanceApi.getTechnicianPerformance).mockRejectedValueOnce(new ApiRequestError(503, 'x'))
    await openPerformance()

    expect(await screen.findByText('The data is temporarily unavailable. Please try again shortly.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'Leaderboard table' })).toBeInTheDocument()
  })

  it('returns to sign-in when the session has expired (401)', async () => {
    vi.mocked(performanceApi.getTechnicianPerformance).mockRejectedValue(
      new ApiRequestError(401, 'Management session is invalid or has expired.'),
    )
    await openPerformance()

    expect(await screen.findByText(/your management session has expired/i)).toBeInTheDocument()
    expect(screen.getByText(/sign in to open technician performance/i)).toBeInTheDocument()
  })
})
