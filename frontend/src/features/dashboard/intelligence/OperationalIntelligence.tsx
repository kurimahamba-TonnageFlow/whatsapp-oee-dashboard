import { useState } from 'react'
import { useProtectedData } from '../../management/session/useProtectedData'
import * as dashboardApi from '../api'
import { DASHBOARD_LINES, PERIOD_OPTIONS } from '../constants'
import { formatCalendarDate, formatMinutes, formatPercent, formatTonnes, localDatePart, MISSING } from '../format'
import type {
  DashboardOverview,
  DashboardWindow,
  LineStopReason,
  RankedLoss,
  TargetStatus,
  WeeklyTargetProgress,
  WeeklyTargetsResponse,
} from '../types'
import { TargetTrack } from '../ui/charts'
import { DataTable, type Column } from '../ui/DataTable'
import { FilterBar, SelectField } from '../ui/filters'
import { MetricCard, MetricGrid, type Tone } from '../ui/MetricCard'
import { PageHeader } from '../ui/PageHeader'
import { Panel } from '../ui/Panel'
import { EmptyState, ErrorState, LoadingState, NotAvailable, Notice, RefreshFailed } from '../ui/states'
import { StatusBadge } from '../ui/StatusBadge'
import { loadWeeklyTrend, weekProgress } from '../weekly'
import { WeeklyTonnageChart } from '../WeeklyTonnageChart'

const DEFAULT_OI_PERIOD: DashboardWindow = 'production_week'

const PACE: Record<TargetStatus, { label: string; tone: Tone }> = {
  green: { label: 'On pace', tone: 'good' },
  red: { label: 'Behind pace', tone: 'bad' },
  grey: { label: 'No status', tone: 'neutral' },
}

interface LossRow extends RankedLoss {
  kind: 'Planned stop' | 'Unplanned (machine)'
  name: string
}

const LOSS_COLUMNS: Column<LossRow>[] = [
  { header: 'Type', render: (row) => row.kind },
  { header: 'Cause', render: (row) => row.name },
  { header: 'Minutes', numeric: true, render: (row) => formatMinutes(row.minutes) },
  { header: 'Est. tonnes lost', numeric: true, render: (row) => formatTonnes(row.estimated_lost_tonnes) },
]

const LINE_STOP_COLUMNS: Column<LineStopReason>[] = [
  { header: 'Line', render: (row) => row.production_line },
  {
    header: 'Type',
    render: (row) => (
      <StatusBadge tone={STOP_TYPE[row.downtime_type].tone}>{STOP_TYPE[row.downtime_type].label}</StatusBadge>
    ),
  },
  { header: 'Reason', render: (row) => row.reason },
  { header: 'Minutes', numeric: true, render: (row) => formatMinutes(row.minutes) },
  {
    header: 'Est. tonnes lost',
    numeric: true,
    render: (row) =>
      row.downtime_type === 'not_scheduled'
        ? 'Not a loss'
        : row.estimated_lost_tonnes === null
          ? MISSING
          : formatTonnes(row.estimated_lost_tonnes),
  },
]

const STOP_TYPE: Record<LineStopReason['downtime_type'], { label: string; tone: 'warn' | 'bad' | 'neutral' }> = {
  planned: { label: 'Planned', tone: 'warn' },
  unplanned: { label: 'Unplanned', tone: 'bad' },
  not_scheduled: { label: 'Not scheduled', tone: 'neutral' },
}

function LineStopsPanel({ overview, periodLabel }: { overview: DashboardOverview; periodLabel: string }) {
  const stops = overview.line_stops
  return (
    <Panel title="Line stops between runs">
      {!stops ? (
        <NotAvailable needed="line_stops on /api/v1/dashboard/overview">Line stops are not reported by this server yet.</NotAvailable>
      ) : stops.by_reason.length === 0 ? (
        <EmptyState>No handover, changeover, Other stop, restart delay or not scheduled time in this period.</EmptyState>
      ) : (
        <>
          <p className="pd-footnote">
            {periodLabel}: {formatMinutes(stops.planned_minutes)} planned · {formatMinutes(stops.unplanned_minutes)}{' '}
            unplanned · {formatMinutes(stops.not_scheduled_minutes ?? 0)} not scheduled (no target, not downtime)
          </p>
          <DataTable
            label="Line stops between runs"
            columns={LINE_STOP_COLUMNS}
            rows={stops.by_reason}
            rowKey={(row) => `${row.production_line}-${row.downtime_type}-${row.reason}`}
          />
        </>
      )}
      {stops && <p className="pd-footnote">{stops.note}</p>}
    </Panel>
  )
}

const LINE_TARGET_COLUMNS: Column<WeeklyTargetProgress>[] = [
  { header: 'Line', render: (row) => row.production_line ?? 'Site' },
  { header: 'Actual', numeric: true, render: (row) => formatTonnes(row.actual_tonnes) },
  { header: 'Target', numeric: true, render: (row) => (row.target_tonnes === null ? 'Not set' : formatTonnes(row.target_tonnes)) },
  { header: 'Needed by now', numeric: true, render: (row) => formatTonnes(row.expected_tonnes_by_now) },
  { header: 'Remaining', numeric: true, render: (row) => formatTonnes(row.tonnes_remaining) },
  {
    header: 'Pace',
    render: (row) => <StatusBadge tone={PACE[row.target_status].tone}>{PACE[row.target_status].label}</StatusBadge>,
  },
]

function lossRows(overview: DashboardOverview): LossRow[] {
  const planned = (overview.gap_attribution.by_planned_reason ?? []).map((item) => ({
    ...item,
    kind: 'Planned stop' as const,
    name: item.reason ?? MISSING,
  }))
  const machines = (overview.gap_attribution.by_machine ?? []).map((item) => ({
    ...item,
    kind: 'Unplanned (machine)' as const,
    name: item.production_line ? `${item.production_line} · ${item.machine}` : (item.machine ?? MISSING),
  }))
  return [...planned, ...machines]
    .filter((row) => row.minutes > 0 || row.estimated_lost_tonnes > 0)
    .sort((a, b) => b.estimated_lost_tonnes - a.estimated_lost_tonnes)
}

export function OperationalIntelligence() {
  const [period, setPeriod] = useState<DashboardWindow>(DEFAULT_OI_PERIOD)
  const [line, setLine] = useState('')

  const overview = useProtectedData(
    (token, signal) => dashboardApi.getOverview(token, { window: period, production_line: line || null }, signal),
    JSON.stringify({ period, line }),
  )
  const trend = useProtectedData((token, signal) => loadWeeklyTrend(token, signal), 'weekly-trend')

  const periodLabel = PERIOD_OPTIONS.find((option) => option.value === period)?.label ?? period

  return (
    <>
      <PageHeader
        title="Operational Intelligence"
        subtitle="Weekly tonnes against target, downtime and the output it cost."
        updatedAt={overview.data?.generated_at ?? null}
        onRefresh={() => {
          overview.reload()
          trend.reload()
        }}
        isRefreshing={overview.isLoading || trend.isLoading}
      />

      <FilterBar
        label="Operational Intelligence filters"
        note="Target figures always cover this production week (Monday 06:00 to Monday 06:00). Period applies to downtime and tonnes lost."
      >
        <SelectField label="Line" value={line} onChange={setLine} options={DASHBOARD_LINES} allLabel="All Lines" />
        <SelectField
          label="Period"
          value={period}
          onChange={(value) => setPeriod(value as DashboardWindow)}
          options={PERIOD_OPTIONS}
        />
      </FilterBar>

      {(overview.error && overview.data) || (trend.error && trend.data) ? (
        <RefreshFailed message={(overview.error ?? trend.error) as string} />
      ) : null}

      <WeeklyTargetSection trend={trend} line={line} />

      {!overview.data && overview.isLoading && <LoadingState>Loading downtime and losses…</LoadingState>}
      {!overview.data && !overview.isLoading && overview.error && (
        <ErrorState message={overview.error} onRetry={overview.reload} />
      )}
      {overview.data && <DowntimeSection overview={overview.data} periodLabel={periodLabel} />}
    </>
  )
}

function WeeklyTargetSection({
  trend,
  line,
}: {
  trend: { data: WeeklyTargetsResponse[] | null; isLoading: boolean; error: string | null; reload: () => void }
  line: string
}) {
  if (!trend.data) {
    if (trend.isLoading) return <LoadingState>Loading the weekly target…</LoadingState>
    if (trend.error) return <ErrorState message={trend.error} onRetry={trend.reload} />
    return null
  }

  const current = trend.data[trend.data.length - 1]
  const progress = weekProgress(current, line)
  const pace = progress ? PACE[progress.target_status] : PACE.grey
  const weekLabel = `Week from ${formatCalendarDate(localDatePart(current.week.start_local))}`
  const hasTarget = progress?.target_tonnes != null

  return (
    <>
      {current.data_quality.legacy_records_excluded && current.data_quality.message && (
        <Notice>{current.data_quality.message}</Notice>
      )}
      <MetricGrid>
        <MetricCard icon="⚖" label="Actual tonnes" value={formatTonnes(progress?.actual_tonnes)} detail={weekLabel} />
        <MetricCard
          icon="◎"
          label="Weekly target"
          value={hasTarget ? formatTonnes(progress?.target_tonnes) : 'Not set'}
          tone={hasTarget ? undefined : 'warn'}
          detail={hasTarget ? `${formatPercent(progress?.percent_complete)} complete` : 'Set in Management weekly targets'}
        />
        <MetricCard
          icon="↘"
          label="Target gap"
          value={hasTarget ? formatTonnes(progress?.tonnes_remaining) : MISSING}
          tone={pace.tone === 'neutral' ? undefined : pace.tone}
          detail={progress?.status_reason ?? 'Still needed to reach the weekly target'}
        />
        <MetricCard
          icon="◷"
          label="Week elapsed"
          value={formatPercent(progress?.week_elapsed_percent)}
          detail={hasTarget ? `Needed by now: ${formatTonnes(progress?.expected_tonnes_by_now)}` : 'Of the production week'}
        />
      </MetricGrid>

      <div className="pd-grid-2">
        <Panel title="Target vs actual">
          {hasTarget && progress?.target_tonnes != null ? (
            <>
              <p>
                <StatusBadge tone={pace.tone}>{pace.label}</StatusBadge>{' '}
                <span className="pd-muted">{progress.status_reason}</span>
              </p>
              <TargetTrack
                actual={progress.actual_tonnes ?? 0}
                target={progress.target_tonnes}
                expectedByNow={progress.expected_tonnes_by_now}
                format={(value) => formatTonnes(value)}
              />
            </>
          ) : (
            <EmptyState title="No weekly target set">
              {progress?.status_reason ?? 'No weekly target has been set for this week.'} Targets are set per week
              by Management (POST /api/v1/management/weekly-targets); nothing is carried forward.
            </EmptyState>
          )}
          <DataTable
            label="Weekly target by line"
            columns={LINE_TARGET_COLUMNS}
            rows={[current.site, ...current.lines]}
            rowKey={(row) => row.production_line ?? 'site'}
          />
          <p className="pd-footnote">{current.pace_method}</p>
        </Panel>

        <Panel title="Tonnage trend">
          <WeeklyTonnageChart weeks={trend.data} line={line} />
        </Panel>
      </div>
    </>
  )
}

function DowntimeSection({ overview, periodLabel }: { overview: DashboardOverview; periodLabel: string }) {
  const gap = overview.gap_attribution
  const hasOutput = overview.output.hourly_update_count > 0
  const rows = lossRows(overview)

  return (
    <>
      {overview.data_quality.legacy_records_excluded && overview.data_quality.message && (
        <Notice>{overview.data_quality.message}</Notice>
      )}
      <MetricGrid>
        <MetricCard
          icon="◷"
          label="Planned downtime"
          value={hasOutput ? formatMinutes(gap.planned_downtime.minutes) : MISSING}
          tone={hasOutput ? 'warn' : undefined}
          detail={hasOutput ? `Est. ${formatTonnes(gap.planned_downtime.estimated_lost_tonnes)} of output · ${periodLabel}` : 'No hourly updates in this period'}
        />
        <MetricCard
          icon="◷"
          label="Unplanned downtime"
          value={hasOutput ? formatMinutes(gap.unplanned_downtime.minutes) : MISSING}
          tone={hasOutput ? 'bad' : undefined}
          detail={hasOutput ? `Est. ${formatTonnes(gap.unplanned_downtime.estimated_lost_tonnes)} of output · ${periodLabel}` : 'No hourly updates in this period'}
        />
        <MetricCard
          icon="⚠"
          label="Estimated tonnes lost"
          value={hasOutput ? formatTonnes(gap.measured_output_gap.estimated_lost_tonnes) : MISSING}
          detail={hasOutput ? `Measured output gap · ${periodLabel}` : 'No hourly updates in this period'}
        />
      </MetricGrid>

      <div className="pd-grid-wide-left">
        <Panel title="Where output was lost">
          {!hasOutput ? (
            <EmptyState>No hourly updates in this period, so no losses can be estimated.</EmptyState>
          ) : rows.length === 0 ? (
            <EmptyState>No downtime was attributed to lost output in this period.</EmptyState>
          ) : (
            <DataTable label="Where output was lost" columns={LOSS_COLUMNS} rows={rows} rowKey={(row) => `${row.kind}-${row.name}`} />
          )}
          <p className="pd-footnote">
            Estimated: downtime minutes converted to output at each run's fixed agreed standard, capped per reporting interval at the observed
            gap. Not explained: {formatTonnes(gap.unexplained_gap.estimated_lost_tonnes)}.
          </p>
        </Panel>

        <Panel title="Downtime trend by week">
          <NotAvailable needed="planned / unplanned downtime for past production weeks (e.g. a week_start parameter on /overview or /gap-attribution)">
            The downtime reports cover the current shift, day, week or last 24 hours only, so earlier weeks
            cannot be compared yet.
          </NotAvailable>
        </Panel>
      </div>

      <LineStopsPanel overview={overview} periodLabel={periodLabel} />
    </>
  )
}
