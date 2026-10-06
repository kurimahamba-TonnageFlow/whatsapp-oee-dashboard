import { OperatingContext } from '../shared/OperatingContext'
import { formatMinutes, formatPallets, formatPercent, formatTonnes, MISSING } from './format'
import type { DashboardOverview, LineSummary, RankedLoss } from './types'
import { BarList, ColumnChart } from './ui/charts'
import { MetricCard, MetricGrid } from './ui/MetricCard'
import { Panel } from './ui/Panel'
import { EmptyState } from './ui/states'

interface DashboardSummaryProps {
  overview: DashboardOverview
  /** The lines in scope (all, or the one selected). */
  lines: LineSummary[]
  scopeLabel: string
  periodLabel: string
}

/** KPI row, then output against target and the reasons for the gap side
 * by side at equal size. Every number is the backend's own figure from
 * GET /api/v1/dashboard/overview. */
export function DashboardSummary({ overview, lines, scopeLabel, periodLabel }: DashboardSummaryProps) {
  const { output } = overview
  const hasOutput = output.hourly_update_count > 0
  const running = lines.filter((line) => line.active_run !== null).length
  const faultLines = lines.filter((line) => line.open_faults > 0).map((line) => line.production_line)
  const noOutput = 'No comparable readings with a known standard'

  return (
    <>
      {overview.reported_palletised_output && <p>
        Total reported palletised output (including legacy runs): {overview.reported_palletised_output.hourly_update_count > 0 ? `${formatTonnes(overview.reported_palletised_output.actual_tonnes)} nominal` : 'Not reported'}.
        Target comparisons below use only readings with a known agreed standard.
      </p>}
      {overview.gap_attribution.reconciliation && !overview.gap_attribution.reconciliation.coverage_complete && <p role="status">
        Reporting coverage is incomplete. Missing readings and unknown standards are excluded from comparisons.
      </p>}
      <MetricGrid>
        <MetricCard
          icon="▥"
          label="Live lines"
          value={`${running} of ${lines.length}`}
          detail={running === 1 ? 'line has an active run' : 'lines have an active run'}
        />
        <MetricCard
          icon="◎"
          label="Expected output"
          value={hasOutput ? formatTonnes(output.expected_tonnes) : MISSING}
          detail={hasOutput ? formatPallets(output.expected_pallets) : noOutput}
        />
        <MetricCard
          icon="⚖"
          label="Actual output"
          value={hasOutput ? formatTonnes(output.actual_tonnes) : MISSING}
          detail={
            !hasOutput
              ? noOutput
              : output.production_achievement_percent === null
                ? 'No expected output to compare against'
                : `${formatPercent(output.production_achievement_percent)} of expected`
          }
        />
        <MetricCard
          icon="↘"
          label="Net output shortfall"
          value={hasOutput ? formatTonnes(output.output_gap_tonnes) : MISSING}
          tone={hasOutput && output.output_gap_tonnes > 0 ? 'bad' : undefined}
          detail={
            !hasOutput
              ? noOutput
              : output.output_gap_tonnes === 0 && output.expected_tonnes > 0
                ? 'Reported output met or beat the comparable target in total; individual periods may still have shortfalls'
                : formatPallets(output.output_gap_pallets)
          }
        />
        <MetricCard
          icon="⚠"
          label="Active faults"
          value={overview.open_faults}
          tone={overview.open_faults > 0 ? 'bad' : 'good'}
          detail={faultLines.length > 0 ? `On ${faultLines.join(', ')}` : 'No open faults'}
        />
      </MetricGrid>

      {hasOutput ? (
        <div className="pd-grid-2">
          <OutputAgainstTarget overview={overview} lines={lines} />
          <ReasonsForGap overview={overview} />
        </div>
      ) : (
        <section className="pd-state pd-state--empty" aria-labelledby="summary-empty-heading">
          <h2 id="summary-empty-heading" className="pd-state__title">
            No comparable production figures yet
          </h2>
          <p>
            No comparable readings with an agreed standard are available for {scopeLabel} in the selected period: {periodLabel}.
            Expected and actual output appear here once line technicians submit hourly updates on the
            HMI.
          </p>
        </section>
      )}
    </>
  )
}

function OutputAgainstTarget({ overview, lines }: { overview: DashboardOverview; lines: LineSummary[] }) {
  const { output } = overview
  const withOutput = lines.filter((line) => line.output.hourly_update_count > 0)

  return (
    <Panel title="Output against target">
      <BarList
        label="Expected against actual output"
        largest={Math.max(output.expected_tonnes, output.actual_tonnes)}
        rows={[
          { label: 'Expected', value: output.expected_tonnes, display: formatTonnes(output.expected_tonnes), tone: 'target' },
          { label: 'Actual', value: output.actual_tonnes, display: formatTonnes(output.actual_tonnes), tone: 'actual' },
        ]}
      />
      {withOutput.length > 1 && (
        <>
          <h3 className="pd-subheading">By line</h3>
          <ColumnChart
            label="Expected against actual output by line"
            series={[
              { key: 'target', label: 'Expected', tone: 'target' },
              { key: 'actual', label: 'Actual', tone: 'actual' },
            ]}
            categories={withOutput.map((line) => ({
              label: line.production_line,
              values: { target: line.output.expected_tonnes, actual: line.output.actual_tonnes },
            }))}
            format={(value) => formatTonnes(value)}
          />
        </>
      )}
      <p className="pd-footnote">
        Expected output is each run's fixed agreed standard over covered scheduled minutes. Actual
        output is reported palletised output, converted using nominal pack weight.
      </p>
    </Panel>
  )
}

function TopContributors({
  title,
  items,
  nameOf,
}: {
  title: string
  items: RankedLoss[]
  nameOf: (item: RankedLoss) => string
}) {
  const top = items.filter((item) => item.estimated_lost_tonnes > 0).slice(0, 3)
  return (
    <div className="pd-contributors">
      <h3 className="pd-subheading">{title}</h3>
      {top.length === 0 ? (
        <p className="pd-muted">None recorded in this period.</p>
      ) : (
        <ol>
          {top.map((item) => (
            <li key={nameOf(item)}>
              <span>{nameOf(item)}</span>
              <span className="pd-muted">{formatMinutes(item.minutes)}</span>
              <strong>{formatTonnes(item.estimated_lost_tonnes)}</strong>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function ReasonsForGap({ overview }: { overview: DashboardOverview }) {
  const gap = overview.gap_attribution
  const planned = gap.planned_downtime
  const unplanned = gap.unplanned_downtime
  const measuredGap = gap.measured_output_gap.estimated_lost_tonnes

  return (
    <Panel title="Production gap reconciliation">
      {gap.reconciliation && <div>
        <p>Net variance (actual minus standard): {gap.reconciliation.signed_variance_packs} packs.
          Positive hourly shortfalls: {gap.reconciliation.shortfall_packs} packs.
          Hourly overproduction: {gap.reconciliation.overproduction_packs} packs.</p>
        <p>Comparable reporting: {gap.reconciliation.covered_periods} of {gap.reconciliation.total_periods} periods.
          {gap.reconciliation.coverage_complete ? ' All comparable periods covered.' : ' Incomplete coverage; this is not a complete shift result.'}</p>
        <p>Raw modelled equivalents: planned {gap.reconciliation.raw_planned_packs}, unplanned {gap.reconciliation.raw_unplanned_packs} packs.
          Excess above observed shortfalls: {gap.reconciliation.excess_modelled_packs} packs.</p>
        <OperatingContext reports={gap.reconciliation.operating_context} />
        {gap.reconciliation.reported_explanations?.map((note,i) => <p key={i}>Reported explanation (not quantified evidence): {note}</p>)}
        {gap.reconciliation.limitations.map(message => <p key={message}>{message}</p>)}
      </div>}
      <p>Shortfalls across reporting periods are added separately; later overproduction does not erase an earlier shortfall. The net output shortfall above offsets overproduction against shortfalls. Reported palletised production uses nominal pack weight. Modelled contributions are not confirmed causes.</p>
      {measuredGap > 0 ? (
        <figure className="pd-chart pd-chart--flat">
          <figcaption className="pd-subheading">
            Where the output gap went (estimated) · {formatTonnes(measuredGap)} measured gap
          </figcaption>
          <BarList
            label="Where the output gap went"
            largest={measuredGap}
            rows={[
              {
                label: 'Planned downtime',
                note: formatMinutes(planned.minutes),
                value: planned.estimated_lost_tonnes,
                display: formatTonnes(planned.estimated_lost_tonnes),
                tone: 'planned',
              },
              {
                label: 'Unplanned downtime',
                note: formatMinutes(unplanned.minutes),
                value: unplanned.estimated_lost_tonnes,
                display: formatTonnes(unplanned.estimated_lost_tonnes),
                tone: 'unplanned',
              },
              {
                label: 'Not explained',
                value: gap.unexplained_gap.estimated_lost_tonnes,
                display: formatTonnes(gap.unexplained_gap.estimated_lost_tonnes),
                tone: 'unexplained',
              },
            ]}
          />
        </figure>
      ) : (
        <EmptyState>There is no output gap to explain in this period.</EmptyState>
      )}
      <div className="pd-grid-2">
        <TopContributors
          title="Top machines (unplanned)"
          items={gap.by_machine ?? []}
          nameOf={(item) => (item.production_line ? `${item.production_line} · ${item.machine}` : (item.machine ?? ''))}
        />
        <TopContributors title="Top planned stops" items={gap.by_planned_reason ?? []} nameOf={(item) => item.reason ?? ''} />
      </div>
      <p className="pd-footnote">
        Estimated: downtime minutes are converted to output at each run's management standard, and never add
        up to more than the measured gap.
      </p>
    </Panel>
  )
}
