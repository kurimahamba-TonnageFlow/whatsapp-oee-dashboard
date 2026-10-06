import { useState } from 'react'
import { useProtectedData } from '../../management/session/useProtectedData'
import * as dashboardApi from '../api'
import { DASHBOARD_LINES } from '../constants'
import {
  addDays,
  formatCalendarDate,
  formatDateTime,
  formatMinutes,
  formatPackWeight,
  formatShortDate,
  londonToday,
  MISSING,
} from '../format'
import type { Changeover, ChangeoverFilters, ChangeoverGroup, ChangeoversResponse } from '../types'
import { BarList } from '../ui/charts'
import { DataTable, type Column } from '../ui/DataTable'
import { DateField, FilterBar, SelectField } from '../ui/filters'
import { MetricCard, MetricGrid } from '../ui/MetricCard'
import { PageHeader } from '../ui/PageHeader'
import { Panel } from '../ui/Panel'
import { EmptyState, ErrorState, LoadingState, NotAvailable, RefreshFailed } from '../ui/states'
import { StatusBadge } from '../ui/StatusBadge'

/** Five production weeks, so the weekly trend has something to compare. */
const DEFAULT_RANGE_DAYS = 34

function defaultFilters(): ChangeoverFilters {
  const today = londonToday()
  return {
    date_from: addDays(today, -DEFAULT_RANGE_DAYS),
    date_to: today,
    production_line: '',
    customer: '',
    product: '',
    status: '',
  }
}

function rangeProblem(filters: ChangeoverFilters): string | null {
  if (!filters.date_from || !filters.date_to) return 'Choose both a start date and an end date.'
  if (filters.date_from > filters.date_to) return 'The start date must be on or before the end date.'
  return null
}

interface QaReport {
  byWeek: ChangeoversResponse
  byLine: ChangeoversResponse
}

/** "New" value, with what it replaced underneath when it changed. */
function Change({ from, to, format = (value) => String(value) }: {
  from: string | number | null
  to: string | number | null
  format?: (value: string | number) => string
}) {
  const shown = (value: string | number | null) => (value === null || value === '' ? MISSING : format(value))
  if (from === to) {
    return (
      <span className="pd-change">
        {shown(to)}
        <small>unchanged</small>
      </span>
    )
  }
  return (
    <span className="pd-change">
      {shown(to)}
      <small>from {shown(from)}</small>
    </span>
  )
}

const LOG_COLUMNS: Column<Changeover>[] = [
  { header: 'Started', render: (row) => formatDateTime(row.started_at) },
  { header: 'Line', render: (row) => row.production_line },
  { header: 'Technician', render: (row) => row.line_technician },
  { header: 'Shift', render: (row) => row.shift },
  { header: 'Product', render: (row) => <Change from={row.previous_product} to={row.new_product} /> },
  { header: 'Customer', render: (row) => <Change from={row.previous_customer} to={row.new_customer} /> },
  {
    header: 'Pack weight',
    render: (row) => (
      <Change
        from={row.previous_pack_weight_kg}
        to={row.new_pack_weight_kg}
        format={(value) => formatPackWeight(Number(value))}
      />
    ),
  },
  { header: 'Format', render: (row) => <Change from={row.previous_format} to={row.new_format} /> },
  {
    header: 'Physical',
    numeric: true,
    render: (row) => (row.physical_minutes == null ? <span className="pd-muted">—</span> : formatMinutes(row.physical_minutes)),
  },
  {
    header: 'New-run setup',
    numeric: true,
    render: (row) => (row.setup_minutes == null ? <span className="pd-muted">—</span> : formatMinutes(row.setup_minutes)),
  },
  {
    header: 'Total',
    numeric: true,
    render: (row) => (row.duration_minutes === null ? <span className="pd-muted">In progress</span> : formatMinutes(row.duration_minutes)),
  },
  {
    header: 'Status',
    render: (row) => <StatusBadge tone={row.status === 'Open' ? 'warn' : 'good'}>{row.status}</StatusBadge>,
  },
]

function groupNote(group: ChangeoverGroup): string {
  const count = `${group.changeover_count} ${group.changeover_count === 1 ? 'changeover' : 'changeovers'}`
  return group.average_duration_minutes === null
    ? `${count} · none completed`
    : `${count} · avg ${formatMinutes(group.average_duration_minutes)}`
}

export function QaDashboard() {
  const [filters, setFilters] = useState<ChangeoverFilters>(defaultFilters)
  const problem = rangeProblem(filters)

  const options = useProtectedData(
    (token, signal) => dashboardApi.getFilterOptions(token, signal),
    'filter-options',
  )

  const report = useProtectedData<QaReport | null>(
    async (token, signal) => {
      if (problem) return null
      const params = {
        date_from: filters.date_from,
        date_to: filters.date_to,
        production_line: filters.production_line || null,
        customer: filters.customer || null,
        product: filters.product || null,
        status: filters.status || null,
      }
      const [byWeek, byLine] = await Promise.all([
        dashboardApi.getChangeovers(token, { ...params, group_by: 'week' }, signal),
        dashboardApi.getChangeovers(token, { ...params, group_by: 'line' }, signal),
      ])
      return { byWeek, byLine }
    },
    JSON.stringify({ ...filters, problem }),
  )

  const data = report.data

  function setFilter(name: keyof ChangeoverFilters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }))
  }

  return (
    <>
      <PageHeader
        title="QA"
        subtitle="Changeovers, their duration and quality status."
        updatedAt={data?.byWeek.generated_at ?? null}
        meta={`${formatCalendarDate(filters.date_from)} to ${formatCalendarDate(filters.date_to)}`}
        onRefresh={() => {
          report.reload()
          options.reload()
        }}
        isRefreshing={report.isLoading}
      />

      <FilterBar
        label="QA filters"
        note="Dates are factory days (06:00 to 06:00 UK time). Customer and product match either side of a changeover."
      >
        <DateField label="From" value={filters.date_from} onChange={(value) => setFilter('date_from', value)} />
        <DateField label="To" value={filters.date_to} onChange={(value) => setFilter('date_to', value)} />
        <SelectField
          label="Line"
          value={filters.production_line}
          onChange={(value) => setFilter('production_line', value)}
          options={DASHBOARD_LINES}
          allLabel="All Lines"
        />
        <SelectField
          label="Customer"
          value={filters.customer}
          onChange={(value) => setFilter('customer', value)}
          options={options.data?.customers ?? []}
          allLabel="All customers"
        />
        <SelectField
          label="Product"
          value={filters.product}
          onChange={(value) => setFilter('product', value)}
          options={options.data?.products ?? []}
          allLabel="All products"
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(value) => setFilter('status', value)}
          options={['Open', 'Completed']}
          allLabel="All statuses"
        />
      </FilterBar>

      {problem && (
        <p className="pd-alert" role="alert">
          {problem}
        </p>
      )}
      {report.error && data && <RefreshFailed message={report.error} />}
      {!problem && !data && report.isLoading && <LoadingState>Loading changeovers…</LoadingState>}
      {!data && !report.isLoading && report.error && <ErrorState message={report.error} onRetry={report.reload} />}

      {data && <QaBody data={data} />}
    </>
  )
}

function QaBody({ data }: { data: QaReport }) {
  const log = data.byWeek.changeovers
  const completed = log.filter((row) => row.status === 'Completed').length
  const open = log.length - completed
  // Weeks in time order (the backend ranks groups by total duration).
  const weeks = [...(data.byWeek.groups ?? [])].sort((a, b) => String(a.key).localeCompare(String(b.key)))
  const lines = data.byLine.groups ?? []
  const busiestWeek = Math.max(0, ...weeks.map((group) => group.changeover_count))
  const longestLine = Math.max(0, ...lines.map((group) => group.total_duration_minutes))

  return (
    <>
      <MetricGrid>
        <MetricCard icon="⤧" label="Total changeovers" value={log.length} detail="Started in the selected dates" />
        <MetricCard icon="✓" label="Completed" value={completed} detail="First acceptable packs produced" />
        <MetricCard
          icon="⟳"
          label="In progress"
          value={open}
          tone={open > 0 ? 'warn' : undefined}
          detail={open > 0 ? 'Not yet completed' : 'None open'}
        />
        <MetricCard
          icon="◇"
          label="Product / customer / format split"
          unavailable="Changeovers are not classified by type yet."
        />
      </MetricGrid>

      <Panel title="Changeover log">
        {log.length === 0 ? (
          <EmptyState>No changeovers were started in the selected dates.</EmptyState>
        ) : (
          <>
            <p className="pd-table-caption">
              {log.length} {log.length === 1 ? 'changeover' : 'changeovers'}, newest first. Each row shows the
              new value, with what it replaced.
            </p>
            <DataTable label="Changeover log" columns={LOG_COLUMNS} rows={log} rowKey={(row) => row.changeover_id} />
          </>
        )}
        <p className="pd-footnote">{data.byWeek.definition}</p>
      </Panel>

      <div className="pd-grid-3">
        <Panel title="Changeovers by week">
          {weeks.length === 0 ? (
            <EmptyState>No changeovers to trend.</EmptyState>
          ) : (
            <BarList
              label="Changeovers by production week"
              largest={busiestWeek}
              rows={weeks.map((group) => ({
                label: `w/c ${formatShortDate(String(group.key))}`,
                note: group.average_duration_minutes === null ? 'none completed' : `avg ${formatMinutes(group.average_duration_minutes)}`,
                value: group.changeover_count,
                display: String(group.changeover_count),
                tone: 'actual',
              }))}
            />
          )}
          <p className="pd-footnote">Production weeks start Monday 06:00.</p>
        </Panel>

        <Panel title="Changeover time by line">
          {lines.length === 0 ? (
            <EmptyState>No changeovers to compare.</EmptyState>
          ) : (
            <BarList
              label="Total changeover time by line"
              largest={longestLine}
              rows={lines.map((group) => ({
                label: String(group.key ?? MISSING),
                note: groupNote(group),
                value: group.total_duration_minutes,
                display: formatMinutes(group.total_duration_minutes),
                tone: 'planned',
              }))}
            />
          )}
          <p className="pd-footnote">Total time of completed changeovers.</p>
        </Panel>

        <div className="pd-stack">
          <Panel title="QA status">
            <NotAvailable needed="a QA check / sign-off recorded against each changeover (a new field and endpoint - a schema change, not built)">
              Pulse does not record a QA check or sign-off for changeovers yet, so no pass, fail or pending
              status can be shown.
            </NotAvailable>
          </Panel>
          <Panel title="Changeovers by type">
            <NotAvailable needed="a changeover type (product / customer / format / pack weight) on each /changeovers row, classified in the backend">
              Previous and new values are recorded (see the log), but the type of each changeover is not
              classified yet.
            </NotAvailable>
          </Panel>
        </div>
      </div>
    </>
  )
}
