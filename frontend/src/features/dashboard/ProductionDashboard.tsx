import catalogue from '../../../../src/production_catalogue.json'
import { useState } from 'react'
import { useProtectedData } from '../management/session/useProtectedData'
import * as dashboardApi from './api'
import { ATTENTION, DASHBOARD_LINES, DEFAULT_PERIOD, PERIOD_OPTIONS, RUNS_PAGE_SIZE } from './constants'
import { DashboardSummary } from './DashboardSummary'
import { HourlyOutput } from './HourlyOutput'
import { formatDateTime, localDatePart } from './format'
import { LinePerformance } from './LinePerformance'
import { LineStopCorrections } from './LineStopCorrections'
import { NextStepDecisions } from './NextStepDecisions'
import { RecentRuns } from './RecentRuns'
import type { DashboardOverview, DashboardRunsResponse, DashboardWindow, RunFilters } from './types'
import { FilterBar, SelectField } from './ui/filters'
import { PageHeader } from './ui/PageHeader'
import { Panel } from './ui/Panel'
import { ErrorState, LoadingState, NotAvailable, Notice, RefreshFailed } from './ui/states'
import { loadWeeklyTrend } from './weekly'
import { WeeklyTonnageChart } from './WeeklyTonnageChart'

const NO_RUN_FILTERS: RunFilters = { technician: '', shift: '', customer: '', product: '' }

interface DashboardReport {
  overview: DashboardOverview
  runs: DashboardRunsResponse
}

function periodLabel(value: DashboardWindow): string {
  return PERIOD_OPTIONS.find((option) => option.value === value)?.label ?? value
}

function attentionHeadline(overview: DashboardOverview, line: string): { text: string; attention: boolean } {
  const lines = overview.lines.filter((summary) => !line || summary.production_line === line)
  const needsAttention = lines
    .filter((summary) => summary.attention_status === 'red' || summary.attention_status === 'amber')
    .sort((a, b) => ATTENTION[a.attention_status].order - ATTENTION[b.attention_status].order)

  if (needsAttention.length > 0) {
    return {
      attention: true,
      text: needsAttention.map((summary) => `${summary.production_line}: ${summary.attention_explanation}`).join(' · '),
    }
  }
  if (lines.length === 0 || lines.every((summary) => summary.attention_status === 'grey')) {
    return { attention: false, text: 'No production data has been recorded for this period yet.' }
  }
  return { attention: false, text: 'No line needs attention in this period.' }
}

export function ProductionDashboard() {
  // Bumped after a manager corrects a line stop, so the hourly view re-reads.
  const [correctionCount, setCorrectionCount] = useState(0)
  const [period, setPeriod] = useState<DashboardWindow>(DEFAULT_PERIOD)
  const [line, setLine] = useState('')
  const [runFilters, setRunFilters] = useState<RunFilters>(NO_RUN_FILTERS)
  const [tonnageView, setTonnageView] = useState<'week' | 'month'>('week')

  const options = useProtectedData(
    (token, signal) => dashboardApi.getFilterOptions(token, signal),
    'filter-options',
  )

  const report = useProtectedData<DashboardReport>(
    async (token, signal) => {
      const overview = await dashboardApi.getOverview(
        token,
        { window: period, production_line: line || null },
        signal,
      )
      // Runs started within the same factory-time window the backend
      // resolved for the overview (its London calendar dates).
      const runs = await dashboardApi.getRuns(
        token,
        {
          date_from: localDatePart(overview.window.start_local),
          date_to: localDatePart(overview.window.end_local),
          production_line: line || null,
          technician: runFilters.technician || null,
          shift: runFilters.shift || null,
          customer: runFilters.customer || null,
          product: runFilters.product || null,
          page_size: RUNS_PAGE_SIZE,
        },
        signal,
      )
      return { overview, runs }
    },
    JSON.stringify({ period, line, ...runFilters }),
  )

  // The line filter is applied on screen (each week's per-line figures
  // are already in the response), so the weekly reads happen once.
  const trend = useProtectedData((token, signal) => loadWeeklyTrend(token, signal), 'weekly-trend')

  const overview = report.data?.overview ?? null
  const hasRunFilters = Object.values(runFilters).some(Boolean)
  const scopedLines = overview ? overview.lines.filter((s) => !line || s.production_line === line) : []
  const headline = overview ? attentionHeadline(overview, line) : null

  function setRunFilter(name: keyof RunFilters, value: string) {
    setRunFilters((current) => ({ ...current, [name]: value }))
  }

  return (
    <>
      <PageHeader
        title="Production"
        subtitle="Live lines and runs, output against target, and where the gap went."
        updatedAt={overview?.generated_at ?? null}
        meta={overview && `Latest recorded activity: ${formatDateTime(overview.freshness.latest_activity_at)}`}
        onRefresh={() => {
          setCorrectionCount((count) => count + 1)
          report.reload()
          options.reload()
          trend.reload()
        }}
        isRefreshing={report.isLoading}
      />

      <FilterBar
        label="Production filters"
        note={
          <>
            Period and line scope the production summary. Technician, shift, customer and product narrow the
            runs table only - the summary figures are calculated per period and line.
            {hasRunFilters && (
              <>
                {' '}
                <button type="button" className="pd-text-button" onClick={() => setRunFilters(NO_RUN_FILTERS)}>
                  Clear technician, shift, customer and product
                </button>
              </>
            )}
          </>
        }
      >
        <SelectField
          label="Period"
          value={period}
          onChange={(value) => setPeriod(value as DashboardWindow)}
          options={PERIOD_OPTIONS}
        />
        <SelectField label="Line" value={line} onChange={setLine} options={DASHBOARD_LINES} allLabel="All Lines" />
        <SelectField
          label="Technician"
          value={runFilters.technician}
          onChange={(value) => setRunFilter('technician', value)}
          options={options.data?.technicians ?? []}
          allLabel="All technicians"
        />
        <SelectField
          label="Shift"
          value={runFilters.shift}
          onChange={(value) => setRunFilter('shift', value)}
          options={(options.data?.shifts ?? []).map((value) => ({
            value,
            label: catalogue.shifts.find(shift => shift.name === value)?.label ?? value,
          }))}
          allLabel="All shifts"
        />
        <SelectField
          label="Customer"
          value={runFilters.customer}
          onChange={(value) => setRunFilter('customer', value)}
          options={options.data?.customers ?? []}
          allLabel="All customers"
        />
        <SelectField
          label="Product"
          value={runFilters.product}
          onChange={(value) => setRunFilter('product', value)}
          options={options.data?.products ?? []}
          allLabel="All products"
        />
      </FilterBar>

      <Notice>Period and Line scope the production summary. Technician, Shift, Customer and Product filter the recent-runs table only. Hourly output has its own shift selector; weekly tonnage has its own week range.</Notice>
      <NextStepDecisions />

      {report.error && report.data && <RefreshFailed message={report.error} />}
      {!report.data && report.isLoading && <LoadingState>Loading production figures…</LoadingState>}
      {!report.data && !report.isLoading && report.error && (
        <ErrorState message={report.error} onRetry={report.reload} />
      )}

      {report.data && overview && headline && (
        <>
          {overview.data_quality.legacy_records_excluded && overview.data_quality.message && (
            <Notice>{overview.data_quality.message}</Notice>
          )}
          {overview.freshness.stale_status === 'stale' && overview.freshness.stale_lines.length > 0 && (
            <Notice>
              No hourly update for over {overview.freshness.stale_after_minutes} minutes on:{' '}
              {overview.freshness.stale_lines.join(', ')}.
            </Notice>
          )}

          <p
            className={`pd-headline${headline.attention ? ' pd-headline--attention' : ''}`}
            aria-label="Which line needs attention"
          >
            {headline.text}
          </p>

          <HourlyOutput line={line} refreshToken={correctionCount} />

          <LineStopCorrections
            onCorrected={() => {
              setCorrectionCount((count) => count + 1)
              report.reload()
            }}
          />

          <DashboardSummary
            overview={overview}
            lines={scopedLines}
            scopeLabel={line || 'any line'}
            periodLabel={periodLabel(period)}
          />

          <RecentRuns runs={report.data.runs} windowLabel={overview.window.label} hasRunFilters={hasRunFilters} />

          <div className="pd-grid-3">
            <Panel
              title="Tonnage by period"
              actions={
                <div className="pd-tabs" role="group" aria-label="Tonnage period">
                  <button type="button" aria-pressed={tonnageView === 'week'} onClick={() => setTonnageView('week')}>
                    Week
                  </button>
                  <button type="button" aria-pressed={tonnageView === 'month'} onClick={() => setTonnageView('month')}>
                    Month
                  </button>
                </div>
              }
            >
              {trend.error && trend.data && <RefreshFailed message={trend.error} />}
              {tonnageView === 'month' ? (
                <NotAvailable needed="a monthly tonnage report (e.g. GET /api/v1/dashboard/monthly-tonnage), calculated like /weekly-targets">
                  Pulse reports tonnage by production week. There is no monthly total yet.
                </NotAvailable>
              ) : trend.data ? (
                <WeeklyTonnageChart weeks={trend.data} line={line} />
              ) : trend.error ? (
                <ErrorState message={trend.error} onRetry={trend.reload} />
              ) : (
                <LoadingState>Loading weekly tonnes…</LoadingState>
              )}
            </Panel>

            <LinePerformance lines={scopedLines} />

            <Panel title="Product performance">
              <NotAvailable needed="output against target by product for a period (e.g. a group_by=product option on /overview)">
                Output against target is reported per line, not per product. The runs table above shows
                each run's product with its own expected and actual tonnes.
              </NotAvailable>
            </Panel>
          </div>
        </>
      )}
    </>
  )
}
