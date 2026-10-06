import { formatDateTime, formatTonnes } from './format'
import type { DashboardRun, DashboardRunsResponse } from './types'
import { DataTable, type Column } from './ui/DataTable'
import type { Tone } from './ui/MetricCard'
import { Panel } from './ui/Panel'
import { EmptyState } from './ui/states'
import { StatusBadge } from './ui/StatusBadge'

interface RecentRunsProps {
  runs: DashboardRunsResponse
  windowLabel: string
  hasRunFilters: boolean
}

const RUN_STATUS_TONE: Record<string, Tone> = { Active: 'good' }

/** A run with no hourly updates says so once, rather than showing zeros. */
function outputCell(run: DashboardRun, value: number | null) {
  return run.hourly_update_count > 0 ? formatTonnes(value) : null
}

const COLUMNS: Column<DashboardRun>[] = [
  { header: 'Line', render: (run) => run.production_line },
  { header: 'Started', render: (run) => formatDateTime(run.started_at) },
  { header: 'Shift', render: (run) => run.shift },
  { header: 'Technician', render: (run) => run.line_technician },
  { header: 'Customer', render: (run) => run.customer },
  { header: 'Product', render: (run) => run.product },
  {
    header: 'Expected',
    numeric: true,
    render: (run) => outputCell(run, run.expected_tonnes) ?? <span className="pd-muted">No hourly updates yet</span>,
  },
  { header: 'Actual', numeric: true, render: (run) => outputCell(run, run.actual_tonnes) },
  { header: 'Gap', numeric: true, render: (run) => outputCell(run, run.output_gap_tonnes) },
  {
    header: 'Status',
    render: (run) => <StatusBadge tone={RUN_STATUS_TONE[run.status] ?? 'neutral'}>{run.status}</StatusBadge>,
  },
]

/** GET /api/v1/dashboard/runs, newest first. Each run's expected,
 * actual and gap come from the API. */
export function RecentRuns({ runs, windowLabel, hasRunFilters }: RecentRunsProps) {
  return (
    <Panel title="Live and recent runs">
      {runs.items.length === 0 ? (
        <EmptyState>
          {hasRunFilters
            ? 'No runs started in this period match the selected technician, shift, customer or product.'
            : 'No runs started in this period.'}
        </EmptyState>
      ) : (
        <>
          <p className="pd-table-caption">
            Runs started in {windowLabel.toLowerCase()} · showing {runs.items.length} of {runs.total},
            newest first.
          </p>
          <DataTable label="Runs" columns={COLUMNS} rows={runs.items} rowKey={(run) => run.run_id} />
        </>
      )}
    </Panel>
  )
}
