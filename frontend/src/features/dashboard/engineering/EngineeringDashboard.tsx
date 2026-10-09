import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useProtectedData } from '../../management/session/useProtectedData'
import * as dashboardApi from '../api'
import { DASHBOARD_LINES, PERIOD_OPTIONS } from '../constants'
import { formatDateTime, formatMinutes, formatTonnes, localDatePart } from '../format'
import type {
  DashboardFault,
  DashboardFaultsResponse,
  DashboardWindow,
  EngineeringClassificationResponse,
  MachineSummary,
  MachinesResponse,
} from '../types'
import { BarList } from '../ui/charts'
import { DataTable, type Column } from '../ui/DataTable'
import { FilterBar, SelectField } from '../ui/filters'
import { MetricCard, MetricGrid } from '../ui/MetricCard'
import { PageHeader } from '../ui/PageHeader'
import { Panel } from '../ui/Panel'
import { EmptyState, ErrorState, LoadingState, Notice, RefreshFailed } from '../ui/states'
import { StatusBadge } from '../ui/StatusBadge'

/** Engineering reads default to the last 24 hours, like the backend. */
const DEFAULT_ENGINEERING_PERIOD: DashboardWindow = 'rolling_24h'

interface RegisterFilters {
  machine: string
  engineer: string
  fault_status: string
}

const NO_REGISTER_FILTERS: RegisterFilters = { machine: '', engineer: '', fault_status: '' }

interface EngineeringReport {
  classification: EngineeringClassificationResponse
  machines: MachinesResponse
  faults: DashboardFaultsResponse
}

const MACHINE_COLUMNS: Column<MachineSummary & { rank: number }>[] = [
  { header: 'Rank', numeric: true, render: (row) => row.rank },
  {
    header: 'Machine',
    render: (row) => (
      <span className="pd-change">
        {row.machine}
        <small>{row.production_line}</small>
      </span>
    ),
  },
  { header: 'Faults', numeric: true, render: (row) => row.fault_count },
  { header: 'Open', numeric: true, render: (row) => row.open_faults },
  { header: 'Downtime', numeric: true, render: (row) => formatMinutes(row.downtime_minutes_in_window) },
  { header: 'Est. lost', numeric: true, render: (row) => formatTonnes(row.estimated_lost_tonnes) },
]

const FAULT_COLUMNS: Column<DashboardFault>[] = [
  { header: 'Fault', render: (fault) => `#${fault.downtime_event_id}` },
  { header: 'Opened', render: (fault) => formatDateTime(fault.opened_at) },
  { header: 'Line', render: (fault) => fault.production_line },
  { header: 'Machine', render: (fault) => fault.machine },
  { header: 'Reason', render: (fault) => <span className="pd-wrap">{fault.reason}</span> },
  {
    header: 'Engineer',
    render: (fault) => fault.engineer ?? <span className="pd-muted">{fault.engineer_called ? 'Not accepted yet' : 'Not called'}</span>,
  },
  {
    header: 'Duration',
    numeric: true,
    render: (fault) => (
      <>
        {formatMinutes(fault.duration_minutes)}
        {fault.duration_is_active && <span className="pd-muted"> so far</span>}
      </>
    ),
  },
  {
    header: 'Production status',
    render: (fault) => (
      <StatusBadge tone={fault.production_status === 'Ongoing' ? 'bad' : 'good'}>
        {fault.production_status === 'Ongoing' ? 'Open' : 'Resolved'}
      </StatusBadge>
    ),
  },
  { header: 'Engineering status', render: (fault) => fault.engineer_called ? fault.engineering_status : 'Not called' },
]

const REPAIR_LABELS = {
  physical_component_failure: 'Mechanical',
  machine_setup_or_setting: 'Machine setting',
  not_classified: 'Not classified',
} as const

const PREVENTABLE_LABELS = {
  yes: 'Yes',
  no: 'No',
  unsure: 'Unsure',
  not_recorded: 'Not recorded',
} as const

function WorkspaceLink() {
  return (
    <a className="pd-link-button pd-link-button--primary" href="/engineering" target="_blank" rel="noopener noreferrer">
      Open Engineering workspace
      <span className="pd-visually-hidden"> (opens in a new tab)</span>
      <span aria-hidden="true">↗</span>
    </a>
  )
}

export function EngineeringDashboard() {
  const [period, setPeriod] = useState<DashboardWindow>(DEFAULT_ENGINEERING_PERIOD)
  const [searchParams] = useSearchParams()
  const [line, setLine] = useState(searchParams.get('line') ?? '')
  const [register, setRegister] = useState<RegisterFilters>(NO_REGISTER_FILTERS)

  const options = useProtectedData(
    (token, signal) => dashboardApi.getFilterOptions(token, signal),
    'filter-options',
  )

  const report = useProtectedData<EngineeringReport>(
    async (token, signal) => {
      const params = { window: period, production_line: line || null }
      const [classification, machines] = await Promise.all([
        dashboardApi.getEngineeringClassification(token, params, signal),
        dashboardApi.getMachines(token, params, signal),
      ])
      // The register lists faults opened on the window's London dates -
      // except Status "Open", which lists every fault open right now,
      // however long ago it was opened.
      const openNow = register.fault_status === 'Ongoing'
      const faults = await dashboardApi.getFaults(
        token,
        {
          date_from: searchParams.get('fault') ? null : openNow ? null : localDatePart(classification.window.start_local),
          date_to: searchParams.get('fault') ? null : openNow ? null : localDatePart(classification.window.end_local),
          production_line: line || null,
          machine: register.machine || null,
          engineer: register.engineer || null,
          fault_status: register.fault_status || null,
        },
        signal,
      )
      return { classification, machines, faults }
    },
    JSON.stringify({ period, line, ...register }),
  )

  const data = report.data
  const hasRegisterFilters = Object.values(register).some(Boolean)

  function setRegisterFilter(name: keyof RegisterFilters, value: string) {
    setRegister((current) => ({ ...current, [name]: value }))
  }

  return (
    <>
      <PageHeader
        title="Engineering"
        subtitle="Open and resolved faults, downtime, recurring problems and the fault register."
        updatedAt={data?.classification.generated_at ?? null}
        meta={data && `Period: ${data.classification.window.label}`}
        onRefresh={() => {
          report.reload()
          options.reload()
        }}
        isRefreshing={report.isLoading}
        actions={<WorkspaceLink />}
      />

      <FilterBar
        label="Engineering filters"
        note={
          <>
            Period and line apply to every figure. Machine, engineer and status narrow the fault register
            only. Faults are accepted, updated and closed in the Engineering workspace (its own sign-in).
            {hasRegisterFilters && (
              <>
                {' '}
                <button type="button" className="pd-text-button" onClick={() => setRegister(NO_REGISTER_FILTERS)}>
                  Clear machine, engineer and status
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
          label="Machine"
          value={register.machine}
          onChange={(value) => setRegisterFilter('machine', value)}
          options={options.data?.machines ?? []}
          allLabel="All machines"
        />
        <SelectField
          label="Engineer"
          value={register.engineer}
          onChange={(value) => setRegisterFilter('engineer', value)}
          options={options.data?.engineers ?? []}
          allLabel="All engineers"
        />
        <SelectField
          label="Status"
          value={register.fault_status}
          onChange={(value) => setRegisterFilter('fault_status', value)}
          options={[
            { value: 'Ongoing', label: 'Open' },
            { value: 'Resolved', label: 'Resolved' },
          ]}
          allLabel="All statuses"
        />
      </FilterBar>

      {report.error && data && <RefreshFailed message={report.error} />}
      {!data && report.isLoading && <LoadingState>Loading engineering figures…</LoadingState>}
      {!data && !report.isLoading && report.error && <ErrorState message={report.error} onRetry={report.reload} />}

      {data && (
        <EngineeringBody
          data={data}
          hasRegisterFilters={hasRegisterFilters}
          openNow={register.fault_status === 'Ongoing'}
          onShowOpen={() => setRegisterFilter('fault_status', 'Ongoing')}
        />
      )}
    </>
  )
}

interface EngineeringBodyProps {
  data: EngineeringReport
  hasRegisterFilters: boolean
  /** The register is showing every fault open now, not the period's. */
  openNow: boolean
  onShowOpen: () => void
}

function EngineeringBody({ data, hasRegisterFilters, openNow, onShowOpen }: EngineeringBodyProps) {
  const [searchParams] = useSearchParams()
  const { classification, machines, faults } = data
  const open = classification.by_status.open
  const closed = classification.by_status.closed
  const preventability = classification.by_maintenance_preventable
  // The open/closed buckets partition every fault in the window, so their
  // downtime adds up to the window's total fault downtime.
  const faultMinutes = open.downtime_minutes_in_window + closed.downtime_minutes_in_window
  const totalFaults = open.fault_count + closed.fault_count
  const answered = preventability.yes.fault_count + preventability.no.fault_count + preventability.unsure.fault_count
  const ranked = machines.machines.map((machine, index) => ({ ...machine, rank: index + 1 }))

  const repairRows = (Object.keys(REPAIR_LABELS) as Array<keyof typeof REPAIR_LABELS>).map((key) => ({
    label: REPAIR_LABELS[key],
    note: formatMinutes(classification.by_repair_classification[key].downtime_minutes_in_window),
    value: classification.by_repair_classification[key].fault_count,
    display: `${classification.by_repair_classification[key].fault_count}`,
    tone: 'neutral' as const,
  }))
  const preventableRows = (Object.keys(PREVENTABLE_LABELS) as Array<keyof typeof PREVENTABLE_LABELS>).map((key) => ({
    label: PREVENTABLE_LABELS[key],
    value: preventability[key].fault_count,
    display: `${preventability[key].fault_count}`,
    tone: 'neutral' as const,
  }))

  return (
    <>
      {classification.data_quality.legacy_records_excluded && classification.data_quality.message && (
        <Notice>{classification.data_quality.message}</Notice>
      )}

      <Notice>Open and resolved refer to production status. Production downtime ends at the recorded restart, even when Engineering work continues. Fault minutes below sum individual events: overlapping faults can count more than once. These are not Engineering labour hours.</Notice>
      <MetricGrid>
        <MetricCard
          icon="⚠"
          label="Open faults"
          value={open.fault_count}
          tone={open.fault_count > 0 ? 'bad' : 'good'}
          detail={`${formatMinutes(open.downtime_minutes_in_window)} downtime so far`}
        />
        <MetricCard
          icon="✓"
          label="Resolved faults"
          value={closed.fault_count}
          detail={`${formatMinutes(closed.downtime_minutes_in_window)} downtime`}
        />
        <MetricCard icon="◷" label="Fault downtime" value={formatMinutes(faultMinutes)} detail="Within the selected period" />
        <MetricCard
          icon="⚒"
          label="Maintenance preventable"
          value={preventability.yes.fault_count}
          detail={answered > 0 ? `of ${answered} faults answered at closure` : 'No closure answers recorded yet'}
        />
        <MetricCard
          icon="◴"
          label="Average fault duration"
          unavailable="Pulse does not calculate an average fault duration yet."
        />
      </MetricGrid>

      <div className="pd-grid-wide-right">
        <Panel title="Recurring problems">
          {ranked.length === 0 ? (
            <EmptyState>No machine faults in this period.</EmptyState>
          ) : (
            <>
              <p className="pd-table-caption">
                Machines ranked by estimated tonnes lost, then downtime. Fault reasons are free text, so
                recurrence is grouped by machine.
              </p>
              <DataTable
                label="Recurring problems by machine"
                columns={MACHINE_COLUMNS}
                rows={ranked}
                rowKey={(row) => `${row.production_line}-${row.machine}`}
              />
            </>
          )}
        </Panel>

        <Panel title="Fault register">{searchParams.get('fault')&&<Notice>Selected fault #{searchParams.get('fault')}. <a href="/dashboard/engineering">Show all faults</a></Notice>}
          {faults.items.length === 0 ? (
            <EmptyState>
              {openNow
                ? 'No faults are open right now that match the selected machine or engineer.'
                : hasRegisterFilters
                  ? 'No faults opened in this period match the selected machine, engineer or status.'
                  : 'No faults were opened in this period.'}
              {!openNow && open.fault_count > 0 && (
                <>
                  {' '}
                  {open.fault_count} {open.fault_count === 1 ? 'fault opened earlier is' : 'faults opened earlier are'}{' '}
                  still open.{' '}
                  <button type="button" className="pd-text-button" onClick={onShowOpen}>
                    Show all open faults
                  </button>
                </>
              )}
            </EmptyState>
          ) : (
            <>
              <p className="pd-table-caption">
                {openNow ? 'Every fault open right now' : "Faults opened on the period's dates"} · {faults.total}{' '}
                {faults.total === 1 ? 'fault' : 'faults'}, newest first.
              </p>
              <DataTable
                label="Fault register"
                columns={FAULT_COLUMNS}
                rows={searchParams.get('fault') ? faults.items.filter(f=>String(f.downtime_event_id)===searchParams.get('fault')) : faults.items}
                rowKey={(fault) => fault.downtime_event_id}
              />
            </>
          )}
        </Panel>
      </div>

      <div className="pd-grid-2">
        <Panel title="Repair classification">
          {totalFaults === 0 ? (
            <EmptyState>No faults in this period.</EmptyState>
          ) : (
            <BarList label="Faults by repair classification" largest={totalFaults} rows={repairRows} />
          )}
          <p className="pd-footnote">Fault counts, with downtime, from each fault's latest classified repair update.</p>
        </Panel>
        <Panel title="Maintenance preventable">
          {totalFaults === 0 ? (
            <EmptyState>No faults in this period.</EmptyState>
          ) : (
            <BarList label="Faults by maintenance preventability" largest={totalFaults} rows={preventableRows} />
          )}
          <p className="pd-footnote">
            Answered by the engineer when a fault is closed; never inferred from notes. Open faults count as
            not recorded.
          </p>
        </Panel>
      </div>
    </>
  )
}
