import { TaskPerformance } from './TaskPerformance'
import { useState } from 'react'
import { useProtectedData } from '../management/session/useProtectedData'
import * as dashboardApi from '../dashboard/api'
import { DASHBOARD_LINES } from '../dashboard/constants'
import { formatCalendarDate, formatPercent, formatTonnes, MISSING } from '../dashboard/format'
import * as performanceApi from './api'
import type {
  PerformanceFilters,
  PerformancePeriod,
  TechnicianPerformanceResponse,
  TechnicianResult,
} from './types'
import '../dashboard/dashboard.css'

const PERFORMANCE_PERIODS: ReadonlyArray<{ value: PerformancePeriod; label: string }> = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'current_week', label: 'This week' },
  { value: 'previous_week', label: 'Last week' },
  { value: 'current_month', label: 'This month' },
  { value: 'previous_month', label: 'Last month' },
  { value: 'current_quarter', label: 'This quarter' },
  { value: 'previous_quarter', label: 'Last quarter' },
  { value: 'current_year', label: 'This year' },
  { value: 'custom', label: 'Custom dates' },
]

const DEFAULT_FILTERS: PerformanceFilters = {
  period: 'current_month',
  date_from: '',
  date_to: '',
  production_line: '',
  shift: '',
  technician: '',
  product: '',
  customer: '',
}

/** A custom range needs both dates, in order; named periods are always valid. */
function customRangeProblem(filters: PerformanceFilters): string | null {
  if (filters.period !== 'custom') return null
  if (!filters.date_from || !filters.date_to) return 'Choose both a start date and an end date.'
  if (filters.date_from > filters.date_to) return 'The start date must be on or before the end date.'
  return null
}

function LabelChip({ label }: { label: string }) {
  // Deliberately neutral for every label: this page informs a
  // conversation, it never signals blame.
  return <span className="pulse-status pulse-status--neutral">{label}</span>
}

export function TechnicianPerformance() {
  const [filters, setFilters] = useState<PerformanceFilters>(DEFAULT_FILTERS)
  const rangeProblem = customRangeProblem(filters)

  const options = useProtectedData(
    (token, signal) => dashboardApi.getFilterOptions(token, signal),
    'filter-options',
  )

  const report = useProtectedData<TechnicianPerformanceResponse | null>(
    (token, signal) =>
      rangeProblem ? Promise.resolve(null) : performanceApi.getTechnicianPerformance(token, filters, signal),
    JSON.stringify({ ...filters, rangeProblem }),
  )

  function setFilter(name: keyof PerformanceFilters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }))
  }

  const data = report.data
  const nothingFound = data && data.ranked.length === 0 && data.insufficient_data.length === 0

  return (
    <section className="pulse-report" aria-labelledby="performance-heading">
      <header className="pulse-report__header">
        <div>
          <h1 id="performance-heading">Line Technician Performance</h1>
          <p className="pulse-report__subtitle">
            Results compare each technician's completed production runs against target output.
            Cancelled and test runs are not counted.
          </p>
        </div>
        <div className="pulse-report__updated">
          <span>
            Last updated:{' '}
            <strong>
              {report.loadedAt
                ? report.loadedAt.toLocaleTimeString('en-GB', {
                    hour: '2-digit',
                    minute: '2-digit',
                    timeZone: 'Europe/London',
                  })
                : MISSING}
            </strong>
          </span>
          <button type="button" className="pulse-button" onClick={report.reload} disabled={report.isLoading}>
            {report.isLoading && data ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <p className="pulse-notice" role="note">
        These figures need management context - line conditions, product mix, staffing and
        equipment all affect output. They should not be used on their own for disciplinary
        decisions.
      </p>

      <form
        className="pulse-filters"
        aria-label="Performance filters"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="pulse-field">
          Period
          <select
            value={filters.period}
            onChange={(event) => setFilter('period', event.target.value)}
          >
            {PERFORMANCE_PERIODS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {filters.period === 'custom' && (
          <>
            <label className="pulse-field">
              From
              <input
                type="date"
                value={filters.date_from}
                onChange={(event) => setFilter('date_from', event.target.value)}
              />
            </label>
            <label className="pulse-field">
              To
              <input
                type="date"
                value={filters.date_to}
                onChange={(event) => setFilter('date_to', event.target.value)}
              />
            </label>
          </>
        )}
        <label className="pulse-field">
          Line
          <select
            value={filters.production_line}
            onChange={(event) => setFilter('production_line', event.target.value)}
          >
            <option value="">All Lines</option>
            {DASHBOARD_LINES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {(
          [
            ['shift', 'Shift', 'All shifts', options.data?.shifts],
            ['technician', 'Technician', 'All technicians', options.data?.technicians],
            ['product', 'Product', 'All products', options.data?.products],
            ['customer', 'Customer', 'All customers', options.data?.customers],
          ] as const
        ).map(([name, label, allLabel, values]) => (
          <label key={name} className="pulse-field">
            {label}
            <select value={filters[name]} onChange={(event) => setFilter(name, event.target.value)}>
              <option value="">{allLabel}</option>
              {(values ?? []).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        ))}
      </form>

      {rangeProblem && (
        <p className="pulse-alert" role="alert">
          {rangeProblem}
        </p>
      )}

      {report.error && data && (
        <p className="pulse-alert" role="alert">
          Could not refresh: {report.error} The results below are from the last successful load.
        </p>
      )}

      {!rangeProblem && !data && report.isLoading && (
        <p className="pulse-panel pulse-state" role="status">
          Loading technician results…
        </p>
      )}

      {!data && !report.isLoading && report.error && (
        <div className="pulse-panel pulse-state" role="alert">
          <p>{report.error}</p>
          <button type="button" className="pulse-button" onClick={report.reload}>
            Try again
          </button>
        </div>
      )}

      {data && (
        <>
          <p className="pulse-report__muted">
            {data.date_from && data.date_to
              ? `${formatCalendarDate(data.date_from)} to ${formatCalendarDate(data.date_to)}`
              : 'All dates'}{' '}
            · Ranked by output achieved against target. Technicians need at least{' '}
            {data.minimum_sample_size} completed runs in the period to be ranked.
            Comparisons use nominal tonnes against preserved management standards, with complete timed reading coverage.
            Dates select completed runs by their London start date; those runs are included in full.
            Results describe production associated with each technician, not skill, effort or responsibility for a stop.
          </p>

          {nothingFound ? (
            <section className="pulse-panel pulse-empty" aria-labelledby="leaderboard-heading">
              <h2 id="leaderboard-heading">No completed runs</h2>
              <p>No completed production runs match these filters, so there is nothing to compare yet.</p>
            </section>
          ) : (
            <>
              <Leaderboard results={data.ranked} />
              <InsufficientData results={data.insufficient_data} minimum={data.minimum_sample_size} />
            </>
          )}
        </>
      )}
      <TaskPerformance />
    </section>
  )
}

function Leaderboard({ results }: { results: TechnicianResult[] }) {
  let rank = 0
  return (
    <section className="pulse-section" aria-labelledby="leaderboard-heading">
      <h2 id="leaderboard-heading" className="pulse-section__title">
        Leaderboard
      </h2>
      {results.length === 0 ? (
        <p className="pulse-panel pulse-report__muted">
          No technician has enough completed runs in this period to be ranked yet.
        </p>
      ) : (
        <div className="pulse-table-wrap" tabIndex={0} role="region" aria-label="Leaderboard table">
          <table className="pulse-table">
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Technician</th>
                <th scope="col" className="pulse-num">Completed runs</th>
                <th scope="col" className="pulse-num">Expected output</th>
                <th scope="col" className="pulse-num">Actual output</th>
                <th scope="col" className="pulse-num">Against target</th>
                <th scope="col" className="pulse-num">Output gap</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => {
                const hasTarget = result.target_achievement_percent !== null
                if (hasTarget) rank += 1
                return (
                  <tr key={result.line_technician}>
                    <td>{hasTarget ? rank : MISSING}</td>
                    <th scope="row">{result.line_technician}</th>
                    <td className="pulse-num">{result.completed_runs}</td>
                    <td className="pulse-num">{formatTonnes(result.expected_tonnes)}</td>
                    <td className="pulse-num">{formatTonnes(result.actual_tonnes)}</td>
                    <td className="pulse-num">
                      {hasTarget ? formatPercent(result.target_achievement_percent) : 'No target data'}{' '}
                      <LabelChip label={result.label} />
                    </td>
                    <td className="pulse-num">{formatTonnes(result.output_gap_tonnes)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function InsufficientData({ results, minimum }: { results: TechnicianResult[]; minimum: number }) {
  if (results.length === 0) return null
  return (
    <section className="pulse-section" aria-labelledby="insufficient-heading">
      <h2 id="insufficient-heading" className="pulse-section__title">
        Not enough evidence to compare
      </h2>
      <p className="pulse-report__muted">
        Fewer than {minimum} completed runs in this period - too few for a fair comparison, so these
        technicians are not ranked. Missing readings or unknown standards also prevent ranking.
      </p>
      <div className="pulse-table-wrap" tabIndex={0} role="region" aria-label="Insufficient data table">
        <table className="pulse-table">
          <thead>
            <tr>
              <th scope="col">Technician</th>
              <th scope="col" className="pulse-num">Completed runs</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result) => (
              <tr key={result.line_technician}>
                <th scope="row">{result.line_technician}</th>
                <td className="pulse-num">{result.completed_runs}</td>
                <td>
                  <LabelChip label="Insufficient data" />
                  {result.reported_tonnes !== undefined && <p>Reported palletised output: {formatTonnes(result.reported_tonnes)}</p>}
                  {result.limitations?.map(message => <p key={message}>{message}</p>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
