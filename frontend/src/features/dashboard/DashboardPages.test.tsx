import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../routes/AppRoutes'
import { ApiRequestError } from '../../api/client'
import * as managementApi from '../management/api'
import * as dashboardApi from './api'
import { addDays, londonToday } from './format'
import type {
  ChangeoversResponse,
  DashboardOverview,
  EngineeringClassificationResponse,
  MachinesResponse,
  WeeklyTargetProgress,
  WeeklyTargetsResponse,
  WindowInfo,
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

const WINDOW: WindowInfo = {
  kind: 'rolling_24h',
  label: 'Last 24 hours',
  timezone: 'Europe/London',
  start: '2026-09-24T09:00:00+00:00',
  end: '2026-09-25T09:00:00+00:00',
  start_local: '2026-09-24T10:00:00+01:00',
  end_local: '2026-09-25T10:00:00+01:00',
}

const DATA_QUALITY = { legacy_records_excluded: false, legacy_record_count: 0, message: null }
const bucket = (fault_count: number, downtime_minutes_in_window: number) => ({ fault_count, downtime_minutes_in_window })

function classification(): EngineeringClassificationResponse {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    window: WINDOW,
    by_repair_classification: {
      machine_setup_or_setting: bucket(1, 20),
      physical_component_failure: bucket(2, 70),
      not_classified: bucket(1, 15),
    },
    by_maintenance_preventable: { yes: bucket(1, 30), no: bucket(1, 40), unsure: bucket(0, 0), not_recorded: bucket(2, 35) },
    by_status: { open: bucket(1, 15), closed: bucket(3, 90) },
    data_quality: DATA_QUALITY,
    notes: [],
  }
}

function machines(): MachinesResponse {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    window: WINDOW,
    ranking_basis: 'estimated_lost_tonnes',
    method: 'test',
    machines: [
      {
        production_line: 'Rovema',
        machine: 'Rovema BV2',
        fault_count: 3,
        open_faults: 1,
        downtime_minutes_in_window: 75,
        maintenance_preventable: { Yes: 1, No: 1, Unsure: 0, not_recorded: 1 },
        estimated_lost_tonnes: 1.5,
        estimated_lost_pallets: 1.5,
        estimated_lost_packs: 1500,
      },
    ],
    data_quality: DATA_QUALITY,
  }
}

const FAULTS = {
  items: [
    {
      downtime_event_id: 781,
      production_run_id: 42,
      production_line: 'Rovema',
      fault_id: 5,
      machine: 'Rovema BV2',
      reason: 'Product trapped in sealing jaws',
      reported_by: 'Alex',
      engineer_called: true,
      production_status: 'Ongoing',
      engineering_status: 'Ongoing',
      engineer: null,
      retrospective: false,
      opened_at: '2026-09-25T08:12:00+00:00',
      resolved_at: null,
      duration_minutes: 36,
      duration_is_active: true,
    },
  ],
  total: 1,
}

function changeovers(groupBy: 'week' | 'line'): ChangeoversResponse {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    definition: 'A changeover starts at Start Changeover and ends at the first acceptable packs.',
    group_by: groupBy,
    groups:
      groupBy === 'week'
        ? [{ key: '2026-09-21', changeover_count: 2, completed_count: 1, open_count: 1, total_duration_minutes: 42, average_duration_minutes: 42, longest_duration_minutes: 42 }]
        : [{ key: 'GIC', changeover_count: 2, completed_count: 1, open_count: 1, total_duration_minutes: 42, average_duration_minutes: 42, longest_duration_minutes: 42 }],
    changeovers: [
      {
        changeover_id: 9,
        production_line: 'GIC',
        line_technician: 'Sam',
        shift: 'Day',
        status: 'Completed',
        started_at: '2026-09-25T07:20:00+00:00',
        completed_at: '2026-09-25T08:02:00+00:00',
        completed_by: 'Sam',
        duration_minutes: 42,
        physical_minutes: 30,
        setup_minutes: 12,
        previous_customer: 'Customer A',
        previous_product: 'Long Grain',
        previous_pack_weight_kg: 1,
        previous_format: 'Bag',
        new_customer: 'Customer A',
        new_product: 'Brown Basmati',
        new_pack_weight_kg: 0.5,
        new_format: 'Bag',
        note: null,
      },
      {
        changeover_id: 10,
        production_line: 'GIC',
        line_technician: 'Sam',
        shift: 'Day',
        status: 'Open',
        started_at: '2026-09-25T09:00:00+00:00',
        completed_at: null,
        completed_by: null,
        duration_minutes: null,
        previous_customer: 'Customer A',
        previous_product: 'Brown Basmati',
        previous_pack_weight_kg: 0.5,
        previous_format: 'Bag',
        new_customer: 'Customer B',
        new_product: 'Brown Basmati',
        new_pack_weight_kg: 0.5,
        new_format: 'Bag',
        note: null,
      },
    ],
  }
}

function progress(overrides: Partial<WeeklyTargetProgress> = {}): WeeklyTargetProgress {
  return {
    scope: 'site',
    production_line: null,
    target_tonnes: 90,
    actual_tonnes: 50,
    tonnes_remaining: 40,
    percent_complete: 55.6,
    expected_tonnes_by_now: 54,
    week_elapsed_percent: 60,
    target_status: 'red',
    status_reason: 'Behind the pace needed to reach the weekly target.',
    ...overrides,
  }
}

function weeklyTargets(weekStart: string | null, site: WeeklyTargetProgress = progress()): WeeklyTargetsResponse {
  const monday = weekStart ?? '2026-09-21'
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    week: { ...WINDOW, kind: 'production_week', label: 'Week', start_local: `${monday}T06:00:00+01:00` },
    latest_activity_at: null,
    pace_method: 'Expected tonnes by now = weekly target x fraction of the week elapsed.',
    site,
    lines: [],
    data_quality: DATA_QUALITY,
  }
}

function overview(): DashboardOverview {
  return {
    generated_at: '2026-09-25T09:30:00+00:00',
    window: { ...WINDOW, kind: 'production_week', label: 'Production week' },
    freshness: { latest_activity_at: null, last_hourly_update_at: null, stale_status: 'current', stale_lines: [], stale_after_minutes: 75 },
    output: {
      expected_packs: 1,
      expected_pallets: 60,
      expected_tonnes: 60,
      actual_packs: 1,
      actual_pallets: 50,
      actual_tonnes: 50,
      output_gap_packs: 1,
      output_gap_pallets: 10,
      output_gap_tonnes: 10,
      production_achievement_percent: 83.3,
      hourly_update_count: 12,
    },
    gap_attribution: {
      calculation_status: 'estimated',
      method: 'test',
      measured_output_gap: { estimated_lost_packs: 1, estimated_lost_pallets: 10, estimated_lost_tonnes: 10 },
      planned_downtime: { estimated_lost_packs: 1, estimated_lost_pallets: 3, estimated_lost_tonnes: 3, minutes: 310 },
      unplanned_downtime: { estimated_lost_packs: 1, estimated_lost_pallets: 5, estimated_lost_tonnes: 5, minutes: 486 },
      other_or_speed_loss: { estimated_lost_packs: 1, estimated_lost_pallets: 1, estimated_lost_tonnes: 1 },
      unexplained_gap: { estimated_lost_packs: 1, estimated_lost_pallets: 1, estimated_lost_tonnes: 1 },
      by_machine: [{ production_line: 'Rovema', machine: 'Rovema BV2', minutes: 200, estimated_lost_packs: 1, estimated_lost_pallets: 4, estimated_lost_tonnes: 4 }],
      by_planned_reason: [{ reason: 'Changeover', minutes: 120, estimated_lost_packs: 1, estimated_lost_pallets: 2, estimated_lost_tonnes: 2 }],
    },
    open_faults: 0,
    lines: [],
    data_quality: DATA_QUALITY,
  }
}

beforeEach(() => {
  vi.mocked(managementApi.login).mockResolvedValue(LOGIN)
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
  vi.mocked(dashboardApi.getFilterOptions).mockResolvedValue({
    production_lines: ['GIC', 'Guill', 'Rovema'],
    shifts: ['Day'],
    products: ['Brown Basmati'],
    customers: ['Customer A'],
    technicians: ['Sam'],
    machines: ['Rovema BV2'],
    engineers: ['Dan'],
  })
  vi.mocked(dashboardApi.getEngineeringClassification).mockResolvedValue(classification())
  vi.mocked(dashboardApi.getMachines).mockResolvedValue(machines())
  vi.mocked(dashboardApi.getFaults).mockResolvedValue(FAULTS)
  vi.mocked(dashboardApi.getChangeovers).mockImplementation(async (_token, params) =>
    changeovers(params.group_by === 'line' ? 'line' : 'week'),
  )
  vi.mocked(dashboardApi.getWeeklyTargets).mockImplementation(async (_token, weekStart) => weeklyTargets(weekStart))
  vi.mocked(dashboardApi.getOverview).mockResolvedValue(overview())
  vi.mocked(dashboardApi.getLineDecisions).mockResolvedValue({ generated_at: '', stale_after_minutes: 75, lines: [] })
  vi.mocked(dashboardApi.getLineStops).mockResolvedValue({ generated_at: '', stops: [] })
  vi.mocked(dashboardApi.getRuns).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
  vi.mocked(dashboardApi.getHourly).mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  // Calls only: beforeEach sets every implementation again.
  vi.clearAllMocks()
})

async function openAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
  fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))
}

function sideNav() {
  return within(screen.getByRole('navigation', { name: 'Primary' }))
}

describe('Dashboard shell', () => {
  it('lists the four pages, marks only the current one, and keeps one session between them', async () => {
    await openAt('/dashboard/engineering')
    await screen.findByRole('heading', { level: 1, name: 'Engineering' })

    for (const page of ['Production', 'Engineering', 'QA', 'Operational Intelligence']) {
      expect(sideNav().getByRole('link', { name: page })).toBeInTheDocument()
    }
    expect(sideNav().getByRole('link', { name: 'Engineering' })).toHaveAttribute('aria-current', 'page')
    expect(sideNav().getByRole('link', { name: 'Production' })).not.toHaveAttribute('aria-current')

    fireEvent.click(sideNav().getByRole('link', { name: 'QA' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'QA' })).toBeInTheDocument()
    expect(sideNav().getByRole('link', { name: 'QA' })).toHaveAttribute('aria-current', 'page')
    expect(sideNav().getByRole('link', { name: 'Engineering' })).not.toHaveAttribute('aria-current')

    fireEvent.click(sideNav().getByRole('link', { name: 'Operational Intelligence' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Operational Intelligence' })).toBeInTheDocument()

    fireEvent.click(sideNav().getByRole('link', { name: 'Production' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Production' })).toBeInTheDocument()
    expect(sideNav().getByRole('link', { name: 'Production' })).toHaveAttribute('aria-current', 'page')

    expect(managementApi.login).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('region', { name: /management session/i })).toHaveTextContent('Signed in as Kuri')
  })

  it('keeps the existing areas one click away, with the Engineering workspace in a new tab', async () => {
    await openAt('/dashboard/qa')
    await screen.findByRole('heading', { level: 1, name: 'QA' })

    expect(sideNav().getByRole('link', { name: 'HMI' })).toHaveAttribute('href', '/hmi')
    expect(sideNav().getByRole('link', { name: 'Management' })).toHaveAttribute('href', '/management')
    expect(sideNav().getByRole('link', { name: 'Performance' })).toHaveAttribute('href', '/management/performance')
    const workspace = sideNav().getByRole('link', { name: /engineering workspace/i })
    expect(workspace).toHaveAttribute('href', '/engineering')
    expect(workspace).toHaveAttribute('target', '_blank')

    fireEvent.click(sideNav().getByRole('link', { name: 'Management' }))
    expect(await screen.findByRole('heading', { level: 1, name: /^management$/i })).toBeInTheDocument()
    expect(managementApi.login).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['/dashboard/engineering', /sign in to open engineering dashboard/i, 'Engineering'],
    ['/dashboard/qa', /sign in to open qa dashboard/i, 'QA'],
    ['/dashboard/operational-intelligence', /sign in to open operational intelligence/i, 'Operational Intelligence'],
  ])('sends a signed-out user from %s to sign-in, then back there', async (path, notice, heading) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByText(notice)).toBeInTheDocument()
    expect(dashboardApi.getOverview).not.toHaveBeenCalled()
    expect(dashboardApi.getChangeovers).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Kuri' } })
    fireEvent.change(screen.getByLabelText(/management pin/i), { target: { value: '1234' } })
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }))

    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('logs out from a dashboard page', async () => {
    await openAt('/dashboard/qa')
    await screen.findByRole('heading', { level: 1, name: 'QA' })

    fireEvent.click(screen.getByRole('button', { name: /log out/i }))

    expect(await screen.findByRole('heading', { name: /management sign in/i })).toBeInTheDocument()
    expect(managementApi.logout).toHaveBeenCalledWith('dash-token')
  })
})

describe('Engineering page', () => {
  it('shows open and resolved faults, downtime, recurring problems and the register from the API', async () => {
    await openAt('/dashboard/engineering')
    await screen.findByRole('heading', { name: 'Recurring problems' })

    expect(dashboardApi.getEngineeringClassification).toHaveBeenCalledWith(
      'dash-token',
      { window: 'rolling_24h', production_line: null },
      expect.any(AbortSignal),
    )
    const card = (name: string) => screen.getByRole('article', { name })
    expect(within(card('Open faults')).getByText('1')).toBeInTheDocument()
    expect(within(card('Resolved faults')).getByText('3')).toBeInTheDocument()
    expect(within(card('Fault downtime')).getByText('1 h 45 min')).toBeInTheDocument()
    expect(within(card('Maintenance preventable')).getByText('of 2 faults answered at closure')).toBeInTheDocument()
    // Not calculated by the backend yet - never estimated here.
    expect(within(card('Average fault duration')).getByText('Data not available yet')).toBeInTheDocument()

    const recurring = screen.getByRole('table', { name: 'Recurring problems by machine' })
    expect(within(recurring).getByText('Rovema BV2')).toBeInTheDocument()
    expect(within(recurring).getByText('1.50 t')).toBeInTheDocument()

    const register = screen.getByRole('table', { name: 'Fault register' })
    expect(within(register).getByText('#781')).toBeInTheDocument()
    expect(within(register).getByText('Not accepted yet')).toBeInTheDocument()
    expect(within(register).getByText('Open')).toBeInTheDocument()
    expect(within(register).getByText(/so far/)).toBeInTheDocument()
  })

  it('sends machine, engineer and status to the register only, with the window dates', async () => {
    await openAt('/dashboard/engineering')
    await screen.findByRole('option', { name: 'Dan' })

    fireEvent.change(screen.getByLabelText('Machine'), { target: { value: 'Rovema BV2' } })
    fireEvent.change(screen.getByLabelText('Engineer'), { target: { value: 'Dan' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'Resolved' } })

    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getFaults).mock.lastCall?.[1]).toEqual({
        date_from: '2026-09-24',
        date_to: '2026-09-25',
        production_line: null,
        machine: 'Rovema BV2',
        engineer: 'Dan',
        fault_status: 'Resolved',
      }),
    )
    for (const call of vi.mocked(dashboardApi.getMachines).mock.calls) {
      expect(Object.keys(call[1])).toEqual(['window', 'production_line'])
    }
  })

  it('offers every open fault when the ones still open were opened before the period', async () => {
    vi.mocked(dashboardApi.getFaults).mockResolvedValueOnce({ items: [], total: 0 })
    await openAt('/dashboard/engineering')
    const register = await screen.findByRole('region', { name: 'Fault register' })

    expect(within(register).getByText(/1 fault opened earlier is still open/)).toBeInTheDocument()
    fireEvent.click(within(register).getByRole('button', { name: 'Show all open faults' }))

    // "Open" means open right now, however long ago it was opened: no date range.
    await waitFor(() =>
      expect(vi.mocked(dashboardApi.getFaults).mock.lastCall?.[1]).toMatchObject({
        date_from: null,
        date_to: null,
        fault_status: 'Ongoing',
      }),
    )
    expect(await within(register).findByText(/every fault open right now/i)).toBeInTheDocument()
  })

  it('links to the Engineering workspace in a new tab', async () => {
    await openAt('/dashboard/engineering')
    await screen.findByRole('heading', { level: 1, name: 'Engineering' })

    const links = screen.getAllByRole('link', { name: /open engineering workspace/i })
    expect(links[0]).toHaveAttribute('href', '/engineering')
    expect(links[0]).toHaveAttribute('target', '_blank')
  })

  it('shows a safe error with Try again', async () => {
    vi.mocked(dashboardApi.getMachines).mockRejectedValueOnce(new ApiRequestError(503, 'down'))
    await openAt('/dashboard/engineering')

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Recurring problems' })).toBeInTheDocument()
  })
})

describe('QA page', () => {
  it('reads changeovers for the last five weeks, grouped by week and by line', async () => {
    await openAt('/dashboard/qa')
    await screen.findByRole('table', { name: 'Changeover log' })

    const today = londonToday()
    const groups = vi.mocked(dashboardApi.getChangeovers).mock.calls.map((call) => call[1])
    expect(groups).toEqual([
      expect.objectContaining({ date_from: addDays(today, -34), date_to: today, group_by: 'week' }),
      expect.objectContaining({ date_from: addDays(today, -34), date_to: today, group_by: 'line' }),
    ])
  })

  it('shows totals and a log with what each changeover changed from and to', async () => {
    await openAt('/dashboard/qa')
    const log = await screen.findByRole('table', { name: 'Changeover log' })

    const card = (name: string) => screen.getByRole('article', { name })
    expect(within(card('Total changeovers')).getByText('2')).toBeInTheDocument()
    expect(within(card('Completed')).getByText('1')).toBeInTheDocument()
    expect(within(card('In progress')).getByText('1')).toBeInTheDocument()

    const first = within(log).getAllByRole('row')[1]
    expect(within(first).getByText('Brown Basmati')).toBeInTheDocument()
    expect(within(first).getByText('from Long Grain')).toBeInTheDocument()
    expect(within(first).getByText('500 g')).toBeInTheDocument()
    expect(within(first).getByText('from 1 kg')).toBeInTheDocument()
    // Physical work + new-run setup = total changeover time.
    expect(within(first).getByText('30 min')).toBeInTheDocument()
    expect(within(first).getByText('12 min')).toBeInTheDocument()
    expect(within(first).getByText('42 min')).toBeInTheDocument()
    expect(within(log).getByRole('columnheader', { name: 'New-run setup' })).toBeInTheDocument()
    expect(within(within(log).getAllByRole('row')[2]).getByText('In progress')).toBeInTheDocument()
  })

  it('keeps legacy QA verification and changeover types explicitly unrecorded', async () => {
    await openAt('/dashboard/qa')
    await screen.findByRole('table', { name: 'Changeover log' })

    expect(within(screen.getByRole('region', { name: 'QA status' })).getByText(/Legacy records have no recorded verification/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Changeovers by type' })).getByText(/Not classified:/)).toBeInTheDocument()
    // No invented pass / pending badges.
    expect(screen.queryByText(/^(pass|fail|pending)$/i)).not.toBeInTheDocument()
  })

  it('needs dates in order before asking the API', async () => {
    await openAt('/dashboard/qa')
    await screen.findByRole('table', { name: 'Changeover log' })
    const calls = vi.mocked(dashboardApi.getChangeovers).mock.calls.length

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-12-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-11-01' } })

    expect(await screen.findByText('The start date must be on or before the end date.')).toBeInTheDocument()
    expect(vi.mocked(dashboardApi.getChangeovers).mock.calls.length).toBe(calls)
  })

  it('explains an empty period', async () => {
    vi.mocked(dashboardApi.getChangeovers).mockImplementation(async (_token, params) => ({
      ...changeovers(params.group_by === 'line' ? 'line' : 'week'),
      groups: [],
      changeovers: [],
    }))
    await openAt('/dashboard/qa')

    expect(await screen.findByText('No changeovers were started in the selected dates.')).toBeInTheDocument()
  })
})

describe('Operational Intelligence page', () => {
  it('shows actual, target, gap and pace for this week, and downtime and losses for the period', async () => {
    await openAt('/dashboard/operational-intelligence')
    await screen.findByRole('heading', { name: 'Where output was lost' })

    const card = (name: string) => screen.getByRole('article', { name })
    expect(within(card('Actual tonnes')).getByText('50.00 t')).toBeInTheDocument()
    expect(within(card('Weekly target')).getByText('90.00 t')).toBeInTheDocument()
    expect(within(card('Target gap')).getByText('40.00 t')).toBeInTheDocument()
    expect(within(card('Planned downtime')).getByText('5 h 10 min')).toBeInTheDocument()
    expect(within(card('Unplanned downtime')).getByText('8 h 06 min')).toBeInTheDocument()
    expect(within(card('Estimated tonnes lost')).getByText('10.00 t')).toBeInTheDocument()

    const target = screen.getByRole('region', { name: 'Target vs actual' })
    expect(within(target).getAllByText('Behind pace').length).toBeGreaterThan(0)
    expect(within(target).getByText(/Needed by now 54.00 t/)).toBeInTheDocument()

    const losses = screen.getByRole('table', { name: 'Where output was lost' })
    const rows = within(losses).getAllByRole('row')
    expect(within(rows[1]).getByText('Rovema · Rovema BV2')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Changeover')).toBeInTheDocument()

    expect(dashboardApi.getOverview).toHaveBeenCalledWith(
      'dash-token',
      { window: 'production_week', production_line: null },
      expect.any(AbortSignal),
    )
  })

  it('says so when no weekly target is set, rather than showing a 0 t target', async () => {
    vi.mocked(dashboardApi.getWeeklyTargets).mockImplementation(async (_token, weekStart) =>
      weeklyTargets(
        weekStart,
        progress({ target_tonnes: null, tonnes_remaining: null, percent_complete: null, expected_tonnes_by_now: null, target_status: 'grey', status_reason: 'No weekly target has been set.' }),
      ),
    )
    await openAt('/dashboard/operational-intelligence')

    expect(await screen.findByRole('heading', { name: 'No weekly target set' })).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Weekly target' })).getByText('Not set')).toBeInTheDocument()
    expect(screen.queryByText('0.00 t')).not.toBeInTheDocument()
  })

  it('says the weekly downtime trend is not available yet', async () => {
    await openAt('/dashboard/operational-intelligence')
    const trend = await screen.findByRole('region', { name: 'Downtime trend by week' })

    expect(within(trend).getByText('Data not available yet')).toBeInTheDocument()
  })
})

describe('Operational Intelligence - line stops between runs', () => {
  it('lists Other and the Restart delay after it as separate unplanned reasons', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue({
      ...overview(),
      line_stops: {
        planned_minutes: 25,
        unplanned_minutes: 75,
        note: 'Stops between product runs belong to the line, not to any run.',
        by_reason: [
          { production_line: 'Guill', downtime_type: 'unplanned', reason: 'Other: Power cut', minutes: 40, estimated_lost_tonnes: 4 },
          { production_line: 'Guill', downtime_type: 'unplanned', reason: 'Restart delay', minutes: 35, estimated_lost_tonnes: 3.5 },
          { production_line: 'Rovema', downtime_type: 'planned', reason: 'Shift handover', minutes: 25, estimated_lost_tonnes: null },
        ],
      },
    })
    await openAt('/dashboard/operational-intelligence')

    const table = await screen.findByRole('table', { name: 'Line stops between runs' })
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getByText('Other: Power cut')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Unplanned')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Restart delay')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Unplanned')).toBeInTheDocument()
    expect(within(rows[3]).getByText('Planned')).toBeInTheDocument()
    expect(screen.getByText(/belong to the line, not to any run/i)).toBeInTheDocument()
  })

  it('says so plainly when there were no line stops in the period', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue({
      ...overview(),
      line_stops: { planned_minutes: 0, unplanned_minutes: 0, note: 'n', by_reason: [] },
    })
    await openAt('/dashboard/operational-intelligence')

    expect(await screen.findByText(/no handover, changeover, other stop, restart delay or not scheduled time/i)).toBeInTheDocument()
  })
})

describe('Operational Intelligence - not scheduled time', () => {
  it('lists Not scheduled as its own type, never as a loss', async () => {
    vi.mocked(dashboardApi.getOverview).mockResolvedValue({
      ...overview(),
      line_stops: {
        planned_minutes: 0,
        unplanned_minutes: 30,
        not_scheduled_minutes: 480,
        note: 'Stops between product runs belong to the line.',
        by_reason: [
          { production_line: 'GIC', downtime_type: 'not_scheduled', reason: 'Not scheduled', minutes: 480, estimated_lost_tonnes: null },
          { production_line: 'Guill', downtime_type: 'unplanned', reason: 'Other: Power cut', minutes: 30, estimated_lost_tonnes: 3 },
        ],
      },
    })
    await openAt('/dashboard/operational-intelligence')

    const table = await screen.findByRole('table', { name: 'Line stops between runs' })
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getAllByText('Not scheduled')).toHaveLength(2)   // type badge and reason
    expect(within(rows[1]).getByText('Not a loss')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Unplanned')).toBeInTheDocument()
    expect(screen.getByText(/8 h 00 min not scheduled \(no target, not downtime\)/)).toBeInTheDocument()
  })
})
