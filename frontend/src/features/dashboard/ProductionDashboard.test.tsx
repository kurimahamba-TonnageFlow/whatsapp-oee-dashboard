import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../routes/AppRoutes'
import { ApiRequestError, apiClient } from '../../api/client'
import * as managementApi from '../management/api'
import * as dashboardApi from './api'
import { availableLine } from '../hmi/hmiTestState'
import type {
  DashboardOverview,
  DashboardRunsResponse,
  LineSummary,
  OutputFigures,
  HourlyReport,
  HourSlot,
  WeeklyTargetProgress,
  WeeklyTargetsResponse,
} from './types'

vi.mock('../management/api')
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
  token: 'dash-token',
  manager_name: 'Kuri',
  expires_at: '2099-01-01T00:00:00+00:00',
}

function output(overrides: Partial<OutputFigures> = {}): OutputFigures {
  return {
    expected_packs: 12500,
    expected_pallets: 12.5,
    expected_tonnes: 12.5,
    actual_packs: 10250,
    actual_pallets: 10.25,
    actual_tonnes: 10.25,
    output_gap_packs: 2250,
    output_gap_pallets: 2.25,
    output_gap_tonnes: 2.25,
    production_achievement_percent: 82,
    hourly_update_count: 6,
    ...overrides,
  }
}

function line(name: string, overrides: Partial<LineSummary> = {}): LineSummary {
  return {
    production_line: name,
    attention_status: 'green',
    attention_explanation: 'Production achievement is 97.0% of expected.',
    open_faults: 0,
    active_run: null,
    output: output({ expected_tonnes: 4, actual_tonnes: 3.9, output_gap_tonnes: 0.1, production_achievement_percent: 97.5 }),
    downtime_minutes: { planned: 10, unplanned: 0 },
    freshness: {
      latest_activity_at: '2026-09-25T09:00:00+00:00',
      last_hourly_update_at: '2026-09-25T09:00:00+00:00',
      stale_status: 'current',
      stale_reason: null,
    },
    ...overrides,
  }
}

function overview(overrides: Partial<DashboardOverview> = {}): DashboardOverview {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    window: {
      kind: 'factory_day',
      label: 'Factory day',
      timezone: 'Europe/London',
      start: '2026-09-25T05:00:00+00:00',
      end: '2026-09-26T05:00:00+00:00',
      start_local: '2026-09-25T06:00:00+01:00',
      end_local: '2026-09-26T06:00:00+01:00',
    },
    freshness: {
      latest_activity_at: '2026-09-25T09:00:00+00:00',
      last_hourly_update_at: '2026-09-25T09:00:00+00:00',
      stale_status: 'current',
      stale_lines: [],
      stale_after_minutes: 75,
    },
    output: output(),
    gap_attribution: {
      calculation_status: 'estimated',
      method: 'test',
      measured_output_gap: { estimated_lost_packs: 2250, estimated_lost_pallets: 2.25, estimated_lost_tonnes: 2.25 },
      planned_downtime: { estimated_lost_packs: 500, estimated_lost_pallets: 0.5, estimated_lost_tonnes: 0.5, minutes: 30 },
      unplanned_downtime: { estimated_lost_packs: 1250, estimated_lost_pallets: 1.25, estimated_lost_tonnes: 1.25, minutes: 75 },
      other_or_speed_loss: { estimated_lost_packs: 300, estimated_lost_pallets: 0.3, estimated_lost_tonnes: 0.3 },
      unexplained_gap: { estimated_lost_packs: 200, estimated_lost_pallets: 0.2, estimated_lost_tonnes: 0.2 },
    },
    open_faults: 1,
    lines: [
      line('Rovema'),
      line('GIC', {
        attention_status: 'red',
        attention_explanation: 'Open fault on this line.',
        open_faults: 1,
        active_run: {
          run_id: 42,
          line_technician: 'Alex',
          shift: 'Days',
          customer: 'Customer A',
          product: 'Product A',
          format: null,
          started_at: '2026-09-25T06:10:00+00:00',
          pallets_remaining: 5,
          total_pallets_completed: 3,
        },
      }),
      line('Guill', {
        attention_status: 'grey',
        attention_explanation: 'No production data in this window.',
        output: output({ hourly_update_count: 0, expected_tonnes: 0, actual_tonnes: 0, output_gap_tonnes: 0, production_achievement_percent: null }),
      }),
    ],
    data_quality: { legacy_records_excluded: false, legacy_record_count: 0, message: null },
    ...overrides,
  }
}

function runs(overrides: Partial<DashboardRunsResponse> = {}): DashboardRunsResponse {
  return {
    items: [
      {
        run_id: 42,
        production_line: 'GIC',
        line_technician: 'Alex',
        shift: 'Days',
        customer: 'Customer A',
        product: 'Product A',
        pack_type: 'Bag',
        status: 'Active',
        started_at: '2026-09-25T06:10:00+00:00',
        finished_at: null,
        total_pallets_completed: 3,
        hourly_update_count: 3,
        expected_tonnes: 7.198,
        actual_tonnes: 5.28,
        output_gap_tonnes: 1.918,
      },
      {
        run_id: 41,
        production_line: 'Rovema',
        line_technician: 'Sam',
        shift: 'Days',
        customer: 'Customer B',
        product: 'Product B',
        pack_type: 'Box',
        status: 'Completed',
        started_at: '2026-09-25T06:00:00+00:00',
        finished_at: '2026-09-25T08:00:00+00:00',
        total_pallets_completed: 0,
        hourly_update_count: 0,
        expected_tonnes: null,
        actual_tonnes: null,
        output_gap_tonnes: null,
      },
    ],
    total: 2,
    page: 1,
    page_size: 25,
    ...overrides,
  }
}

function progress(overrides: Partial<WeeklyTargetProgress> = {}): WeeklyTargetProgress {
  return {
    scope: 'site',
    production_line: null,
    target_tonnes: 120,
    actual_tonnes: 80,
    tonnes_remaining: 40,
    percent_complete: 66.7,
    expected_tonnes_by_now: 72,
    week_elapsed_percent: 60,
    target_status: 'green',
    status_reason: 'On or ahead of the pace needed to reach the weekly target.',
    ...overrides,
  }
}

/** /weekly-targets for the Monday asked about (null = this week, 21 Sep). */
function weeklyTargets(weekStart: string | null): WeeklyTargetsResponse {
  const monday = weekStart ?? '2026-09-21'
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    week: {
      kind: 'production_week',
      label: `Production week from ${monday}`,
      timezone: 'Europe/London',
      start: `${monday}T05:00:00+00:00`,
      end: `${monday}T05:00:00+00:00`,
      start_local: `${monday}T06:00:00+01:00`,
      end_local: `${monday}T06:00:00+01:00`,
    },
    latest_activity_at: null,
    pace_method: 'Linear pace.',
    site: progress(weekStart === null ? {} : { actual_tonnes: 100, target_tonnes: null }),
    lines: [progress({ scope: 'line', production_line: 'GIC', actual_tonnes: 30, target_tonnes: 50 })],
    data_quality: { legacy_records_excluded: false, legacy_record_count: 0, message: null },
  }
}

function slot(label: string, hourStart: string): HourSlot {
  const stops = { stopped_minutes: 0, planned_minutes: 0, unplanned_minutes: 0, stop_reasons: [] }
  return {
    hour_start: hourStart,
    hour_end: hourStart,
    hour_label: label,
    is_complete: true,
    line: {
      status: 'reported', target_packs: 6000, actual_packs: 5400, output_vs_target_percent: 90,
      is_low_output: false, covered_minutes: 60, unaccounted_minutes: 0, stoppage_reference_missing: false, ...stops,
    },
    runs: [
      {
        run_id: 42, product: 'Product A', customer: 'Customer A', line_technician: 'Alex', status: 'reported',
        applicable_start: hourStart, applicable_end: hourStart, applicable_minutes: 60, is_partial_hour: false,
        target_speeds: [{ from: hourStart, to: hourStart, speed_ppm: 100 }], actual_speed_ppm: 90,
        target_packs: 6000, actual_packs: 5400, output_vs_target_percent: 90, is_low_output: false, ...stops,
      },
    ],
  }
}

function hourlyReport(): HourlyReport {
  const low = slot('07:00–08:00', '2026-09-25T06:00:00+00:00')
  const reasons = [{ kind: 'unplanned' as const, reason: 'Casepacker — Open cases', minutes: 25 }]
  low.line = {
    ...low.line, output_vs_target_percent: 45, is_low_output: true, actual_packs: 2700,
    stopped_minutes: 25, unplanned_minutes: 25, stop_reasons: reasons,
  }
  low.runs = [{
    ...low.runs[0], output_vs_target_percent: 45, is_low_output: true, actual_packs: 2700,
    actual_speed_ppm: 45, stopped_minutes: 25, unplanned_minutes: 25, stop_reasons: reasons,
  }]
  const missed = slot('08:00–09:00', '2026-09-25T07:00:00+00:00')
  missed.line = { ...missed.line, status: 'no_reading', actual_packs: null, output_vs_target_percent: null }
  missed.runs = [{
    ...missed.runs[0], status: 'no_reading', actual_packs: null, output_vs_target_percent: null,
    actual_speed_ppm: null,
  }]
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    window: {
      kind: 'current_shift', label: 'Day shift 2026-09-25', timezone: 'Europe/London',
      start: '2026-09-25T05:00:00+00:00', end: '2026-09-25T13:00:00+00:00',
      start_local: '2026-09-25T06:00:00+01:00', end_local: '2026-09-25T14:00:00+01:00',
    },
    measure: 'Output vs target (all stops)',
    method: 'Output vs target (all stops) = actual packs / target packs.',
    low_output_percent: 60,
    denominators: { run: 'Run denominator.', line: 'Line denominator.' },
    lines: [
      {
        production_line: 'GIC',
        latest_completed_hour: slot('09:00–10:00', '2026-09-25T08:00:00+00:00'),
        hours: [
          slot('06:00–07:00', '2026-09-25T05:00:00+00:00'),
          low,
          missed,
          slot('09:00–10:00', '2026-09-25T08:00:00+00:00'),
        ],
      },
    ],
  }
}

beforeEach(() => {
  vi.mocked(dashboardApi.getHourly).mockResolvedValue(hourlyReport())
  vi.mocked(dashboardApi.getWeeklyTargets).mockImplementation(async (_token, weekStart) => weeklyTargets(weekStart))
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
  vi.mocked(dashboardApi.getOverview).mockResolvedValue(overview())
  vi.mocked(dashboardApi.getLineDecisions).mockResolvedValue(decisions([]))
  vi.mocked(dashboardApi.getLineStops).mockResolvedValue({ generated_at: '', stops: [] })
  vi.mocked(dashboardApi.getRuns).mockResolvedValue(runs())
  vi.mocked(dashboardApi.getFilterOptions).mockResolvedValue({
    production_lines: ['GIC', 'Guill', 'Rovema'],
    shifts: ['Days', 'Nights'],
    products: ['Product A', 'Product B'],
    customers: ['Customer A', 'Customer B'],
    technicians: ['Alex', 'Sam'],
  })
})

afterEach(() => {
  cleanup()
  vi.mocked(managementApi.login).mockReset()
  vi.mocked(managementApi.logout).mockReset()
  vi.mocked(dashboardApi.getOverview).mockReset()
  vi.mocked(dashboardApi.getRuns).mockReset()
  vi.mocked(dashboardApi.getFilterOptions).mockReset()
  vi.mocked(dashboardApi.getWeeklyTargets).mockReset()
  vi.mocked(dashboardApi.getHourly).mockReset()
  vi.mocked(dashboardApi.getLineDecisions).mockReset()
  vi.mocked(dashboardApi.resolveNextStep).mockReset()
  vi.mocked(dashboardApi.getLineStops).mockReset()
  vi.mocked(dashboardApi.reclassifyLineStop).mockReset()
  vi.mocked(apiClient.get).mockClear()
})

function decisions(lines: Array<{ production_line: string; finished_at: string } | null>) {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    stale_after_minutes: 75,
    lines: lines.filter(Boolean).map((line, index) => ({
      ...availableLine({ line_id: index + 1, production_line: line!.production_line }),
      awaiting_next_step: { run_id: 40 + index, line_technician: 'Sam', finished_at: line!.finished_at },
    })),
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

async function openDashboard() {
  vi.mocked(managementApi.login).mockResolvedValue(LOGIN)
  renderAt('/dashboard')
  fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
  fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
  await screen.findByRole('heading', { level: 1, name: 'Production' })
}

function card(label: string) {
  return screen.getByRole('heading', { level: 3, name: label }).closest('article') as HTMLElement
}

describe('Production Dashboard - access', () => {
  it('requires a Management session and never reads dashboard data while signed out', () => {
    renderAt('/dashboard')

    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(screen.getByText(/sign in to open production dashboard/i)).toBeInTheDocument()
    expect(dashboardApi.getOverview).not.toHaveBeenCalled()
    expect(dashboardApi.getRuns).not.toHaveBeenCalled()
  })

  it('reads with the shared session token', async () => {
    await openDashboard()

    await waitFor(() => expect(dashboardApi.getOverview).toHaveBeenCalled())
    expect(vi.mocked(dashboardApi.getOverview).mock.calls[0][0]).toBe('dash-token')
    expect(vi.mocked(dashboardApi.getFilterOptions).mock.calls[0][0]).toBe('dash-token')
  })
})

describe('Production Dashboard - data', () => {
  it('shows the summary cards with the backend figures, formatted', async () => {
    await openDashboard()
    await screen.findByRole('heading', { name: 'Output against target' })

    expect(within(card('Live lines')).getByText('1 of 3')).toBeInTheDocument()
    expect(within(card('Expected output')).getByText('12.50 t')).toBeInTheDocument()
    expect(within(card('Expected output')).getByText('12.5 pallets')).toBeInTheDocument()
    expect(within(card('Actual output')).getByText('10.25 t')).toBeInTheDocument()
    expect(within(card('Actual output')).getByText('82.0% of expected')).toBeInTheDocument()
    expect(within(card('Net output shortfall')).getByText('2.25 t')).toBeInTheDocument()
    expect(within(card('Active faults')).getByText('1')).toBeInTheDocument()
    expect(within(card('Active faults')).getByText('On GIC')).toBeInTheDocument()
  })

  it('shows output against target and the reasons for the gap side by side, at equal size', async () => {
    await openDashboard()
    const outputPanel = await screen.findByRole('region', { name: 'Output against target' })
    const reasons = screen.getByRole('region', { name: 'Production gap reconciliation' })

    // 09:30 UTC in September = 10:30 BST.
    expect(screen.getByText(/Last updated:/).textContent).toContain('10:30')
    // Same equal-width row: neither is demoted below the other.
    expect(outputPanel.parentElement).toBe(reasons.parentElement)
    expect(outputPanel.parentElement).toHaveClass('pd-grid-2')

    const vsTarget = within(outputPanel).getByRole('list', { name: 'Expected against actual output' })
    expect(within(vsTarget).getByText('12.50 t')).toBeInTheDocument()
    expect(within(vsTarget).getByText('10.25 t')).toBeInTheDocument()

    const breakdown = within(reasons).getByRole('list', { name: 'Where the output gap went' })
    expect(within(breakdown).getByText('30 min')).toBeInTheDocument()
    expect(within(breakdown).getByText('0.50 t')).toBeInTheDocument()
    expect(within(breakdown).getByText('1 h 15 min')).toBeInTheDocument()
    expect(within(breakdown).getByText('1.25 t')).toBeInTheDocument()
    expect(within(breakdown).queryByText('Modelled operating-speed deficit')).not.toBeInTheDocument()
    expect(within(breakdown).queryByText('0.30 t')).not.toBeInTheDocument()
    expect(within(breakdown).getByText('Not explained')).toBeInTheDocument()
  })

  it('names the line that needs attention and lists lines worst first', async () => {
    await openDashboard()

    expect(await screen.findByLabelText('Which line needs attention')).toHaveTextContent(
      'GIC: Open fault on this line.',
    )
    const lineHeadings = within(screen.getByRole('region', { name: 'Line performance' }))
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent)
    expect(lineHeadings).toEqual(['GIC', 'Rovema', 'Guill'])

    const gic = screen.getByRole('article', { name: 'GIC' })
    expect(within(gic).getByText('Needs attention')).toBeInTheDocument()
    expect(within(gic).getByText('Running: Product A for Customer A · Alex · 1 open fault')).toBeInTheDocument()
    const guill = screen.getByRole('article', { name: 'Guill' })
    expect(within(guill).getByText('No production data')).toBeInTheDocument()
    expect(within(guill).getByText('No hourly updates in this period.')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Rovema' })).getByText('On target')).toBeInTheDocument()
  })

  it('says so when no line needs attention', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue(overview({ lines: [line('Rovema'), line('GIC')] }))
    await openDashboard()

    expect(await screen.findByLabelText('Which line needs attention')).toHaveTextContent(
      'No line needs attention in this period.',
    )
  })

  it('shows recent runs with each run’s own expected, actual and gap', async () => {
    await openDashboard()
    const table = await screen.findByRole('table', { name: 'Runs' })

    const rows = within(table).getAllByRole('row')
    expect(within(rows[0]).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Line', 'Started', 'Shift', 'Technician', 'Customer', 'Product', 'Expected', 'Actual', 'Gap', 'Status',
    ])
    expect(within(rows[1]).getByText('7.20 t')).toBeInTheDocument()
    expect(within(rows[1]).getByText('5.28 t')).toBeInTheDocument()
    expect(within(rows[1]).getByText('1.92 t')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Active')).toBeInTheDocument()
    // A run with no hourly updates says so - never 0.00 t.
    expect(within(rows[2]).getByText('No hourly updates yet')).toBeInTheDocument()
    expect(within(rows[2]).queryByText('0.00 t')).not.toBeInTheDocument()
    expect(screen.getByText(/showing 2 of 2/)).toBeInTheDocument()
  })

  it('shows the data-quality message whenever older records are excluded', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue(
      overview({
        data_quality: {
          legacy_records_excluded: true,
          legacy_record_count: 3,
          message: '3 older hourly updates could not be included.',
        },
      }),
    )
    await openDashboard()

    expect(await screen.findByText('3 older hourly updates could not be included.')).toBeInTheDocument()
  })

  it('never presents OEE as a figure', async () => {
    await openDashboard()
    await screen.findByRole('heading', { name: 'Output against target' })

    // OEE may only ever appear in a disclaimer that says it is NOT OEE.
    for (const element of screen.queryAllByText(/OEE/i)) {
      expect(element.textContent).toMatch(/not OEE/i)
    }
  })
})

describe('Production Dashboard - filters', () => {
  it('asks for today by default and the matching run dates', async () => {
    await openDashboard()

    await waitFor(() => expect(dashboardApi.getRuns).toHaveBeenCalled())
    expect(vi.mocked(dashboardApi.getOverview).mock.calls[0][1]).toEqual({
      window: 'factory_day',
      production_line: null,
    })
    expect(vi.mocked(dashboardApi.getRuns).mock.calls[0][1]).toEqual({
      date_from: '2026-09-25',
      date_to: '2026-09-26',
      production_line: null,
      technician: null,
      shift: null,
      customer: null,
      product: null,
      page_size: 25,
    })
  })

  it('offers All Lines, Rovema, GIC and Guill, and re-reads for the chosen line', async () => {
    await openDashboard()
    const lineSelect = screen.getByLabelText('Line')
    expect(within(lineSelect).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'All Lines', 'Rovema', 'GIC', 'Guill',
    ])

    fireEvent.change(lineSelect, { target: { value: 'GIC' } })

    await waitFor(() =>
      expect(dashboardApi.getOverview).toHaveBeenLastCalledWith(
        'dash-token',
        { window: 'factory_day', production_line: 'GIC' },
        expect.any(AbortSignal),
      ),
    )
    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getRuns).mock.lastCall?.[1].production_line).toBe('GIC'),
    )
  })

  it('shows only the selected line’s card when a line is chosen', async () => {
    await openDashboard()
    await screen.findByRole('article', { name: 'GIC' })

    fireEvent.change(screen.getByLabelText('Line'), { target: { value: 'Rovema' } })

    await waitFor(() => expect(screen.queryByRole('article', { name: 'GIC' })).not.toBeInTheDocument())
    expect(screen.getByRole('article', { name: 'Rovema' })).toBeInTheDocument()
  })

  it('changes the period', async () => {
    await openDashboard()

    fireEvent.change(screen.getByLabelText('Period'), { target: { value: 'production_week' } })

    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getOverview).mock.lastCall?.[1]).toEqual({
        window: 'production_week',
        production_line: null,
      }),
    )
  })

  it('applies shift, customer and product to the runs table and can clear them', async () => {
    await openDashboard()
    expect(screen.getByText(/Technician, Shift, Customer and Product filter the recent-runs table only/)).toBeInTheDocument()
    await screen.findByRole('option', { name: 'Nights 22:00 to 06:00' })

    fireEvent.change(screen.getByLabelText('Shift'), { target: { value: 'Nights' } })
    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: 'Customer B' } })
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'Product B' } })

    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getRuns).mock.lastCall?.[1]).toMatchObject({
        shift: 'Nights',
        customer: 'Customer B',
        product: 'Product B',
      }),
    )
    // The summary endpoint has no such filters - it is never sent them.
    for (const call of vi.mocked(dashboardApi.getOverview).mock.calls) {
      expect(Object.keys(call[1])).toEqual(['window', 'production_line'])
    }
    expect(screen.getByText(/narrow the runs table only/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /clear technician, shift, customer and product/i }))
    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getRuns).mock.lastCall?.[1]).toMatchObject({
        shift: null,
        customer: null,
        product: null,
      }),
    )
  })

  it('explains an empty runs table under run filters', async () => {
    vi.mocked(dashboardApi.getRuns).mockResolvedValue(runs({ items: [], total: 0 }))
    await openDashboard()
    await screen.findByRole('option', { name: 'Nights 22:00 to 06:00' })

    fireEvent.change(screen.getByLabelText('Shift'), { target: { value: 'Nights' } })

    expect(
      await screen.findByText('No runs started in this period match the selected technician, shift, customer or product.'),
    ).toBeInTheDocument()
  })

  it('refreshes on demand', async () => {
    await openDashboard()
    await screen.findByRole('heading', { name: 'Output against target' })
    const hourlyCalls = vi.mocked(dashboardApi.getHourly).mock.calls.length
    const calls = vi.mocked(dashboardApi.getOverview).mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(vi.mocked(dashboardApi.getOverview).mock.calls.length).toBe(calls + 1))
    await waitFor(() => expect(vi.mocked(dashboardApi.getHourly).mock.calls.length).toBe(hourlyCalls + 1))
  })
})

describe('Production Dashboard - states', () => {
  it('shows a loading state until the first figures arrive', async () => {
    vi.mocked(dashboardApi.getOverview).mockReturnValue(new Promise(() => {}))
    await openDashboard()

    expect(screen.getByText('Loading production figures…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Output against target' })).not.toBeInTheDocument()
  })

  it('shows a clear empty state instead of zeros when nothing was recorded', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue(
      overview({
        output: output({
          hourly_update_count: 0,
          expected_tonnes: 0,
          actual_tonnes: 0,
          output_gap_tonnes: 0,
          production_achievement_percent: null,
        }),
        lines: [line('Rovema', { attention_status: 'grey', attention_explanation: 'No production data in this window.' })],
      }),
    )
    vi.mocked(dashboardApi.getRuns).mockResolvedValue(runs({ items: [], total: 0 }))
    await openDashboard()

    expect(await screen.findByRole('heading', { name: 'No comparable production figures yet' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Output against target' })).not.toBeInTheDocument()
    expect(screen.getByText('No runs started in this period.')).toBeInTheDocument()
    expect(screen.getByLabelText('Which line needs attention')).toHaveTextContent(
      'No production data has been recorded for this period yet.',
    )
  })

  it('shows a safe error with Try again, and recovers', async () => {
    vi.mocked(dashboardApi.getOverview).mockRejectedValueOnce(
      new ApiRequestError(503, 'Dashboard data is temporarily unavailable. Please try again.'),
    )
    await openDashboard()

    expect(await screen.findByText('The data is temporarily unavailable. Please try again shortly.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: 'Output against target' })).toBeInTheDocument()
  })

  it('shows a network error in plain language', async () => {
    vi.mocked(dashboardApi.getOverview).mockRejectedValue(new ApiRequestError(0, 'offline'))
    await openDashboard()

    expect(await screen.findByText(/could not reach the pulse server/i)).toBeInTheDocument()
  })

  it('keeps the last figures on screen when a refresh fails', async () => {
    await openDashboard()
    await screen.findByRole('heading', { name: 'Output against target' })
    vi.mocked(dashboardApi.getOverview).mockRejectedValueOnce(new ApiRequestError(500, 'boom'))

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    expect(await screen.findByText(/could not refresh/i)).toBeInTheDocument()
    expect(within(card('Expected output')).getByText('12.50 t')).toBeInTheDocument()
  })

  it('returns to sign-in when the session has expired (401), remembering the dashboard', async () => {
    vi.mocked(dashboardApi.getOverview).mockRejectedValue(
      new ApiRequestError(401, 'Management session is invalid or has expired.'),
    )
    await openDashboard()

    expect(await screen.findByText(/your management session has expired/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(screen.getByText(/sign in to open production dashboard/i)).toBeInTheDocument()
  })

  it('handles missing values without inventing zeros', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue(
      overview({ output: output({ production_achievement_percent: null }) }),
    )
    vi.mocked(dashboardApi.getRuns).mockResolvedValue(
      runs({
        items: [{ ...runs().items[0], expected_tonnes: null, actual_tonnes: 5.28, output_gap_tonnes: null }],
        total: 1,
      }),
    )
    await openDashboard()

    expect(await screen.findByText('No expected output to compare against')).toBeInTheDocument()
    const row = within(await screen.findByRole('table', { name: 'Runs' })).getAllByRole('row')[1]
    expect(within(row).getAllByText('—')).toHaveLength(2)
  })
})

describe('Production Dashboard - tonnage and honest gaps', () => {
  it('reads this week and the five before it from /weekly-targets, oldest first', async () => {
    await openDashboard()
    const chart = await screen.findByRole('table', { name: /weekly tonnes against target/i })

    const asked = vi.mocked(dashboardApi.getWeeklyTargets).mock.calls.map((call) => call[1])
    expect(asked).toEqual([null, '2026-08-17', '2026-08-24', '2026-08-31', '2026-09-07', '2026-09-14'])
    const rows = within(chart).getAllByRole('row')
    expect(within(rows[1]).getByRole('rowheader')).toHaveTextContent('17 Aug')
    // A week with no target shows "Not set", never 0.
    expect(within(rows[1]).getByText('Not set')).toBeInTheDocument()
    expect(within(rows[6]).getByRole('rowheader')).toHaveTextContent('This week')
    expect(within(rows[6]).getByText('120.00 t')).toBeInTheDocument()
    expect(within(rows[6]).getByText('80.00 t')).toBeInTheDocument()
  })

  it('shows the selected line’s weekly figures', async () => {
    await openDashboard()
    await screen.findByRole('table', { name: /weekly tonnes against target/i })

    fireEvent.change(screen.getByLabelText('Line'), { target: { value: 'GIC' } })

    const chart = await screen.findByRole('table', { name: 'Weekly tonnes against target - GIC' })
    const thisWeek = within(chart).getAllByRole('row')[6]
    expect(within(thisWeek).getByText('50.00 t')).toBeInTheDocument()
    expect(within(thisWeek).getByText('30.00 t')).toBeInTheDocument()
  })

  it('says monthly tonnage and product performance are not available yet, instead of inventing them', async () => {
    await openDashboard()
    const tonnage = await screen.findByRole('region', { name: 'Tonnage by period' })

    fireEvent.click(within(tonnage).getByRole('button', { name: 'Month' }))
    expect(within(tonnage).getByText('Data not available yet')).toBeInTheDocument()
    expect(within(tonnage).queryByText(/monthly-tonnage/)).not.toBeInTheDocument()

    const product = screen.getByRole('region', { name: 'Product performance' })
    expect(within(product).getByText('Data not available yet')).toBeInTheDocument()
  })

  it('keeps the rest of the page when the weekly figures fail', async () => {
    vi.mocked(dashboardApi.getWeeklyTargets).mockRejectedValue(new ApiRequestError(503, 'down'))
    await openDashboard()

    const tonnage = await screen.findByRole('region', { name: 'Tonnage by period' })
    expect(await within(tonnage).findByText(/temporarily unavailable/i)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Output against target' })).toBeInTheDocument()
  })
})

describe('Production Dashboard - fixed-hour output', () => {
  it('shows each line’s latest completed hour and the earlier hours, newest first', async () => {
    await openDashboard()
    const hourly = await screen.findByRole('region', { name: /by hour/i })

    const latest = await within(hourly).findByLabelText('GIC latest completed hour')
    expect(within(latest).getByText(/09:00–10:00/)).toBeInTheDocument()
    expect(within(latest).getByText('90.0%')).toBeInTheDocument()
    expect(within(latest).getByText('Product A · Alex')).toBeInTheDocument()

    const table = within(hourly).getByRole('table', { name: 'GIC hours' })
    const headers = within(table).getAllByRole('columnheader').map((cell) => cell.textContent)
    expect(headers).toEqual([
      'Hour', 'Product', 'Technician', 'Target speed', 'Actual speed', 'Output vs target (all stops)', 'Stopped',
      'Stops and reasons',
    ])
    const labels = within(table).getAllByRole('rowheader').map((cell) => cell.textContent)
    expect(labels).toEqual(['09:00–10:00', '08:00–09:00', '07:00–08:00', '06:00–07:00'])
  })

  it('shows an unreported hour as No reading, never 0%', async () => {
    await openDashboard()
    const table = await screen.findByRole('table', { name: 'GIC hours' })

    const missedRow = within(table).getByRole('rowheader', { name: '08:00–09:00' }).closest('tr') as HTMLElement
    expect(within(missedRow).getByText('No reading')).toBeInTheDocument()
    expect(within(missedRow).queryByText('0.0%')).not.toBeInTheDocument()
  })

  it('shows below 60% in orange, with its stopped minutes and reason beside it', async () => {
    await openDashboard()
    const table = await screen.findByRole('table', { name: 'GIC hours' })

    const lowRow = within(table).getByRole('rowheader', { name: '07:00–08:00' }).closest('tr') as HTMLElement
    expect(within(lowRow).getByText('45.0%')).toHaveClass('pd-hour__pct--low')
    expect(within(lowRow).getByText('25 min')).toBeInTheDocument()
    expect(within(lowRow).getByText(/Casepacker — Open cases/)).toBeInTheDocument()
    expect(within(lowRow).getByText('45.0')).toBeInTheDocument()
  })

  it('labels the measure honestly and never as OEE', async () => {
    await openDashboard()
    await screen.findByRole('table', { name: 'GIC hours' })

    expect(screen.getByText(/quality is not measured, so this is\s+not oee/i)).toBeInTheDocument()
  })

  it('switches to the previous shift and follows the line filter', async () => {
    await openDashboard()
    await screen.findByRole('table', { name: 'GIC hours' })

    fireEvent.change(screen.getByLabelText('Hourly view shift'), { target: { value: '1' } })
    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getHourly).mock.lastCall?.[1]).toEqual({ shift_offset: 1, production_line: null }),
    )

    fireEvent.change(screen.getByLabelText('Line'), { target: { value: 'GIC' } })
    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getHourly).mock.lastCall?.[1]).toEqual({ shift_offset: 1, production_line: 'GIC' }),
    )
  })
})

describe('Production Dashboard - run ended, next step not chosen', () => {
  it('shows nothing when every ended run has its next step', async () => {
    await openDashboard()
    await waitFor(() => expect(dashboardApi.getLineDecisions).toHaveBeenCalled())
    expect(screen.queryByRole('heading', { name: /next step not chosen/i })).not.toBeInTheDocument()
  })

  it('keeps an old decision visible and lets a manager record it', async () => {
    vi.mocked(dashboardApi.getLineDecisions).mockResolvedValue(
      decisions([{ production_line: 'Rovema', finished_at: '2026-09-22T21:40:00+00:00' }]),
    )
    vi.mocked(dashboardApi.resolveNextStep).mockResolvedValue({} as never)
    await openDashboard()

    const row = await screen.findByLabelText('Rovema next step')
    expect(within(row).getByText(/sam's run ended/i)).toBeInTheDocument()
    expect(screen.getByText(/cannot start on these lines until this is recorded/i)).toBeInTheDocument()

    fireEvent.click(within(row).getByLabelText('Other'))
    fireEvent.click(within(row).getByRole('button', { name: /record as manager/i }))
    expect(await within(row).findByText(/write the reason/i)).toBeInTheDocument()
    expect(dashboardApi.resolveNextStep).not.toHaveBeenCalled()

    fireEvent.change(within(row).getByLabelText('Reason'), { target: { value: 'No orders' } })
    fireEvent.click(within(row).getByRole('button', { name: /record as manager/i }))

    await waitFor(() => expect(dashboardApi.resolveNextStep).toHaveBeenCalledTimes(1))
    const [token, line, payload, key] = vi.mocked(dashboardApi.resolveNextStep).mock.calls[0]
    expect([token, line, payload]).toEqual(['dash-token', 'Rovema', { kind: 'other', reason: 'No orders' }])
    expect(key).toMatch(/^k-/)
    // Re-read so the resolved line drops off the list.
    await waitFor(() => expect(vi.mocked(dashboardApi.getLineDecisions).mock.calls.length).toBeGreaterThan(1))
  })

  it('a retry after a failed save reuses the same key, so it cannot record twice', async () => {
    vi.mocked(dashboardApi.getLineDecisions).mockResolvedValue(
      decisions([{ production_line: 'GIC', finished_at: '2026-09-25T05:10:00+00:00' }]),
    )
    vi.mocked(dashboardApi.resolveNextStep)
      .mockRejectedValueOnce(new ApiRequestError(0, 'offline'))
      .mockResolvedValue({} as never)
    await openDashboard()

    const row = await screen.findByLabelText('GIC next step')
    fireEvent.click(within(row).getByLabelText('End Shift (handover)'))
    fireEvent.click(within(row).getByRole('button', { name: /record as manager/i }))
    expect(await within(row).findByText(/nothing was recorded/i)).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: /record as manager/i }))

    await waitFor(() => expect(dashboardApi.resolveNextStep).toHaveBeenCalledTimes(2))
    const [first, second] = vi.mocked(dashboardApi.resolveNextStep).mock.calls
    expect(second[3]).toBe(first[3])
  })
})

describe('Production Dashboard - not scheduled time', () => {
  it('shows a not scheduled hour with no percentage and a Not scheduled reason, not downtime', async () => {
    const report = hourlyReport()
    const quiet = slot('10:00–11:00', '2026-09-25T09:00:00+00:00')
    quiet.runs = []
    quiet.line = {
      ...quiet.line, status: 'not_scheduled', target_packs: 0, actual_packs: null, output_vs_target_percent: null,
      not_scheduled_minutes: 60, stopped_minutes: 0,
      stop_reasons: [{ kind: 'not_scheduled', reason: 'Not scheduled', minutes: 60 }],
    }
    report.lines[0].hours.push(quiet)
    vi.mocked(dashboardApi.getHourly).mockResolvedValue(report)
    await openDashboard()

    const table = await screen.findByRole('table', { name: 'GIC hours' })
    const row = within(table).getByText('10:00–11:00').closest('tr') as HTMLElement
    expect(within(row).getAllByText('Not scheduled')).toHaveLength(2)   // measure and reason chip
    expect(within(row).getByText(/not scheduled to produce \(no target, not downtime\)/)).toBeInTheDocument()
    expect(within(row).getByText('0 min')).toBeInTheDocument()          // stopped minutes stay 0
    expect(within(row).queryByText(/%$/)).not.toBeInTheDocument()
  })
})

function logStop(overrides: Partial<import('./types').LineStopLogEntry> = {}): import('./types').LineStopLogEntry {
  return {
    stoppage_id: 7, production_line: 'GIC', kind: 'other', downtime_type: 'unplanned', reason: 'No orders',
    started_by: 'Priya (manager)', started_at: '2026-09-24T19:40:00+00:00', ended_by: null, ended_at: null,
    is_open: true, minutes: 820, follows_stoppage_id: null,
    allowed_reclassifications: ['handover', 'other', 'not_scheduled'], reclassifications: [], ...overrides,
  }
}

describe('Production Dashboard - correcting a line stop', () => {
  it('lists the stops and records a correction with the reason for it', async () => {
    vi.mocked(dashboardApi.getLineStops).mockResolvedValue({ generated_at: '', stops: [logStop()] })
    vi.mocked(dashboardApi.reclassifyLineStop).mockResolvedValue({} as never)
    await openDashboard()

    const item = await screen.findByLabelText('Line stop 7')
    expect(within(item).getByText('Other: No orders')).toBeInTheDocument()
    fireEvent.click(within(item).getByRole('button', { name: 'Correct' }))
    expect(within(item).getByLabelText('Correct to')).toHaveValue('handover')
    fireEvent.change(within(item).getByLabelText('Correct to'), { target: { value: 'not_scheduled' } })
    fireEvent.click(within(item).getByRole('button', { name: /save correction/i }))
    expect(await within(item).findByText(/say why this correction is being made/i)).toBeInTheDocument()
    expect(dashboardApi.reclassifyLineStop).not.toHaveBeenCalled()

    fireEvent.change(within(item).getByLabelText('Why the change'), { target: { value: 'Not on the plan' } })
    const hourlyReads = vi.mocked(dashboardApi.getHourly).mock.calls.length
    fireEvent.click(within(item).getByRole('button', { name: /save correction/i }))

    await waitFor(() => expect(dashboardApi.reclassifyLineStop).toHaveBeenCalledTimes(1))
    const [token, id, payload, key] = vi.mocked(dashboardApi.reclassifyLineStop).mock.calls[0]
    expect([token, id, payload]).toEqual([
      'dash-token', 7, { new_kind: 'not_scheduled', reason: null, note: 'Not on the plan' },
    ])
    expect(key).toMatch(/^k-/)
    // The log and the hourly view are read again, so the report reflects the correction.
    await waitFor(() => expect(vi.mocked(dashboardApi.getLineStops).mock.calls.length).toBeGreaterThan(1))
    await waitFor(() => expect(vi.mocked(dashboardApi.getHourly).mock.calls.length).toBeGreaterThan(hourlyReads))
  })

  it('shows every earlier correction with who, when and why', async () => {
    vi.mocked(dashboardApi.getLineStops).mockResolvedValue({
      generated_at: '',
      stops: [
        logStop({
          kind: 'not_scheduled', downtime_type: 'not_scheduled', reason: null,
          reclassifications: [{
            reclassification_id: 3, previous_kind: 'other', previous_reason: 'No orders', new_kind: 'not_scheduled',
            new_reason: null, changed_by: 'Priya', changed_at: '2026-09-25T08:15:00+00:00', note: 'Not on the plan',
          }],
        }),
      ],
    })
    await openDashboard()

    const history = await screen.findByRole('list', { name: 'Corrections to line stop 7' })
    expect(within(history).getByText('Other: No orders')).toBeInTheDocument()
    expect(within(history).getByText('Not scheduled')).toBeInTheDocument()
    expect(within(history).getByText(/by Priya/)).toBeInTheDocument()
    expect(within(history).getByText(/“Not on the plan”/)).toBeInTheDocument()
  })

  it('offers no correction for a changeover, and a retry reuses the same key', async () => {
    vi.mocked(dashboardApi.getLineStops).mockResolvedValue({
      generated_at: '',
      stops: [
        logStop({ stoppage_id: 8, kind: 'changeover', downtime_type: 'planned', reason: null, allowed_reclassifications: [] }),
        logStop(),
      ],
    })
    vi.mocked(dashboardApi.reclassifyLineStop)
      .mockRejectedValueOnce(new ApiRequestError(0, 'offline'))
      .mockResolvedValue({} as never)
    await openDashboard()

    const changeover = await screen.findByLabelText('Line stop 8')
    expect(within(changeover).queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument()

    const item = screen.getByLabelText('Line stop 7')
    fireEvent.click(within(item).getByRole('button', { name: 'Correct' }))
    fireEvent.change(within(item).getByLabelText('Why the change'), { target: { value: 'Shift ended' } })
    fireEvent.click(within(item).getByRole('button', { name: /save correction/i }))
    expect(await within(item).findByText(/nothing was changed/i)).toBeInTheDocument()
    fireEvent.click(within(item).getByRole('button', { name: /save correction/i }))

    await waitFor(() => expect(dashboardApi.reclassifyLineStop).toHaveBeenCalledTimes(2))
    const [first, second] = vi.mocked(dashboardApi.reclassifyLineStop).mock.calls
    expect(second[3]).toBe(first[3])
  })
})


describe('Dashboard snag regressions', () => {
  it('keeps hourly refresh failures visible after a successful load', async () => {
    await openDashboard()
    await waitFor(() => expect(dashboardApi.getHourly).toHaveBeenCalled())
    vi.mocked(dashboardApi.getHourly).mockRejectedValue(new Error('offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText(/Could not refresh: The data could not be loaded/)).toBeInTheDocument()
  })

  it('distinguishes reported legacy output from no readings', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue(overview({
      lines: [line('GIC', {
        output: output({ hourly_update_count: 0 }),
        reported_palletised_output: output({ actual_tonnes: 4 }),
      })],
    }))
    await openDashboard()
    expect(await screen.findByText(/Output reported: 4.00 t nominal/)).toBeInTheDocument()
  })
})


it('discloses a weekly refresh failure after weekly figures loaded', async () => {
  await openDashboard()
  await waitFor(() => expect(dashboardApi.getWeeklyTargets).toHaveBeenCalledTimes(6))
  await waitFor(() => expect(screen.queryByText(/Loading weekly tonnes/)).not.toBeInTheDocument())
  vi.mocked(dashboardApi.getWeeklyTargets).mockRejectedValue(new Error('offline'))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
  expect(await screen.findByText(/Could not refresh: The data could not be loaded/)).toBeInTheDocument()
})
