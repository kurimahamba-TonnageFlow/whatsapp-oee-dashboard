import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useProtectedData } from '../../management/session/useProtectedData'
import { getOperationalIntelligence } from '../api'
import type { DashboardWindow } from '../types'
import { formatMinutes } from '../format'
import { ErrorState, LoadingState, RefreshFailed } from '../ui/states'
import { FinancialIntelligenceProvider, FinancialPreviewButton, Phase2FinancialMetric } from './Phase2FinancialMetric'
import type { IntelligenceSnapshot } from './types'
import './operational-intelligence.css'

const n = (value: number | null | undefined, digits = 1) => value == null ? '\u2014' : value.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const tonnes = (value: number | null | undefined) => value == null ? 'No data' : `${n(value)} t`
const pct = (value: number | null | undefined) => value == null ? '\u2014' : `${n(value)}%`
const stamp = (value: string) => new Date(value).toLocaleString('en-GB', { timeZone: 'Europe/London', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const periodOptions: [DashboardWindow, string][] = [['production_week', 'This production week'], ['current_shift', 'Current shift'], ['factory_day', 'Today from 06:00'], ['rolling_24h', 'Last 24 hours']]
function Section({ title, children, className = '', note }: { title: string; children: ReactNode; className?: string; note?: string }) {
  return <section className={`oi-panel ${className}`} aria-label={title}><div className="oi-section-head"><h2>{title}</h2>{note && <small>{note}</small>}</div>{children}</section>
}
function Icon({ kind }: { kind: 'cost' | 'truck' | 'target' | 'loss' | 'clock' }) {
  const paths = { cost: 'M5 8c0-4 14-4 14 0s-14 4-14 0m0 0v5c0 4 14 4 14 0V8M5 13v5c0 4 14 4 14 0v-5', truck: 'M2 5h12v13H2zM14 10h5l3 4v4h-8M5 18a2 2 0 1 0 4 0m7 0a2 2 0 1 0 4 0', target: 'M20 11a8 8 0 1 1-7-7M16 12a4 4 0 1 1-4-4M12 12l9-9m-1 0h-4m5 0v4', loss: 'M18 5a9 9 0 1 0 3 10M18 2v5h-5M9 17l6-10', clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 6v7l4 2' }
  return <span className={`oi-icon oi-icon--${kind}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]}/></svg></span>
}
function Kpi({ title, kind, children, detail }: { title: string; kind: 'cost' | 'truck' | 'target' | 'loss' | 'clock'; children: ReactNode; detail: ReactNode }) {
  return <article className="oi-kpi" aria-label={title}><Icon kind={kind}/><div><h2>{title}</h2>{children}<div className="oi-kpi__detail">{detail}</div></div></article>
}
function CommercialPreview() {
  const [weeks, setWeeks] = useState('6')
  const categories = ['Downtime', 'Rework', 'Changeovers', 'Labour Overtime', 'Yield Loss', 'Utilities']
  return <Section title="Commercial Performance Overview" className="oi-commercial">
    <div className="oi-commercial__grid">
      <div className="oi-inset oi-trend"><div className="oi-section-head"><h3>Cost per Tonne Trend</h3><label className="oi-mini-select"><span className="sr-only">Financial preview period</span><select value={weeks} onChange={e => setWeeks(e.target.value)}><option value="6">Last 6 weeks</option><option value="12">Last 12 weeks</option></select></label></div>
        <div className="oi-chart-legend"><span className="oi-dot oi-blue"/> Cost trend preview <span className="oi-dashed"/> Target preview</div>
        <FinancialPreviewButton className="oi-trend__chart" label="Unlock Financial Trends in Phase 2">
          <svg viewBox="0 0 660 145" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="oi-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#36a7f4" stopOpacity=".16"/><stop offset="1" stopColor="#36a7f4" stopOpacity="0"/></linearGradient></defs>{[20,48,76,104,132].map(y => <path key={y} d={`M10 ${y}H650`} stroke="#293b46"/>)}{[30,150,270,390,510,630].map(x => <path key={x} d={`M${x} 15V132`} stroke="#24343d"/>)}<path d="M30 35L150 49L270 67L390 82L510 91L630 99V132H30Z" fill="url(#oi-area)"/><path d="M30 35L150 49L270 67L390 82L510 91L630 99" fill="none" stroke="#39aafa" strokeWidth="2.5"/>{[[30,35],[150,49],[270,67],[390,82],[510,91],[630,99]].map(([x,y]) => <circle key={x} cx={x} cy={y} r="4" fill="#d5f0ff" stroke="#39aafa" strokeWidth="2"/>)}<path d="M10 115H650" stroke="#7cda49" strokeWidth="2" strokeDasharray="6 5"/></svg>
          <span className="oi-chart-unlock">Unlock Financial Trends in Phase 2</span>
          <span className="oi-chart-weeks">{Array.from({ length: 6 }, (_, i) => <span key={i}>Week {weeks === '6' ? i + 1 : (i + 1) * 2}</span>)}</span>
        </FinancialPreviewButton><p className="oi-phase-note">PHASE 2 {'\u2014'} Illustration Only</p>
      </div>
      <div className="oi-inset oi-costs"><div className="oi-section-head"><h3>Where Cost Is Building Up</h3><span className="oi-phase">PHASE 2</span></div><p className="oi-caption">Feature preview {'\u2014'} bars are illustrative, not measured costs.</p>
        {categories.map((category, i) => <div className={`oi-cost-row oi-cost-row--${i}`} key={category}><span className="oi-cost-marker" aria-hidden="true"/><span>{category}</span><div className="oi-cost-bar" aria-hidden="true"><i style={{ width: `${80 - i * 10}%` }}/></div><Phase2FinancialMetric label={category} unit="/ t" compact/></div>)}
      </div>
      <div className="oi-inset oi-cost-total"><h3>Total cost per tonne</h3><Phase2FinancialMetric label="Total cost per tonne" unit="/ t"/><hr/><h3>Target</h3><Phase2FinancialMetric label="Target cost per tonne" unit="/ t" compact/><p className="oi-caption">Future financial intelligence</p></div>
    </div>
  </Section>
}
function LossDetails({ data }: { data: IntelligenceSnapshot }) {
  const gap = data.output_gap
  return <Section title="Recoverable vs Confirmed Loss" className="oi-loss">
    <div className="oi-loss__body"><div className={`oi-donut ${gap.total_tonnes == null || gap.total_tonnes === 0 ? 'oi-donut--empty' : ''}`} role="img" aria-label={`${tonnes(gap.total_tonnes)} measured output gap; recoverability not assessed`}><div><strong>{tonnes(gap.total_tonnes)}</strong><small>Measured gap</small></div></div>
      <div className="oi-loss-legend"><div><span className="oi-dot oi-amber"/><p><strong>{tonnes(gap.unclassified_tonnes)}</strong><small>Unclassified output gap</small></p></div><div><span className="oi-dot oi-green"/><p>Recoverable capacity<small>Not assessed</small></p></div><div><span className="oi-dot oi-blue"/><p>Delayed output<small>Not verified</small></p></div><div><span className="oi-dot oi-red"/><p>Confirmed unrecovered loss<small>Not verified</small></p></div></div>
    </div><p className="oi-caption">{gap.note}</p>
  </Section>
}
function StopDetails({ data }: { data: IntelligenceSnapshot }) {
  const stops = data.line_stops
  return <details className="oi-details"><summary>Line stops between runs &amp; data notes</summary><p>{formatMinutes(stops.planned_minutes)} planned {'\u2014'} {formatMinutes(stops.unplanned_minutes)} unplanned {'\u2014'} {formatMinutes(stops.not_scheduled_minutes ?? 0)} not scheduled (no target, not downtime)</p>{stops.by_reason.length ? <table aria-label="Line stops between runs"><thead><tr><th>Line</th><th>Type</th><th>Reason</th><th>Minutes</th><th>Est. tonnes lost</th></tr></thead><tbody>{stops.by_reason.map((row, i) => <tr key={i}><td>{row.production_line}</td><td>{row.downtime_type === 'not_scheduled' ? 'Not scheduled' : row.downtime_type === 'planned' ? 'Planned' : 'Unplanned'}</td><td>{row.reason}</td><td>{formatMinutes(row.minutes)}</td><td>{row.downtime_type === 'not_scheduled' ? 'Not a loss' : tonnes(row.estimated_lost_tonnes)}</td></tr>)}</tbody></table> : <p>No handover, changeover, Other stop, restart delay or not scheduled time in this period.</p>}<p>{stops.note}</p><p>{data.weekly.method}</p>{data.data_issues.map(issue => <p key={issue}>{issue}</p>)}</details>
}
export function OperationalIntelligenceView({ data, error, loading, refresh, period, onPeriod, line, onLine }: { data: IntelligenceSnapshot | null; error: string | null; loading: boolean; refresh: () => void; period: DashboardWindow; onPeriod: (value: DashboardWindow) => void; line: string; onLine: (value: string) => void }) {
  const d = data?.downtime
  const total = d ? d.planned_minutes + d.unplanned_minutes : 0
  return <FinancialIntelligenceProvider><div className="oi">
    <header className="oi-header"><div><h1>Operational Intelligence</h1><p>Profitability, production performance and where cost builds up.</p></div><div className="oi-filters"><label>Site / line<select value={line} onChange={e => onLine(e.target.value)}><option value="">All Lines</option>{(data?.configured_lines ?? ['Rovema', 'GIC', 'Guill']).map(name => <option key={name}>{name}</option>)}</select></label><label>Reporting period<select value={period} onChange={e => onPeriod(e.target.value as DashboardWindow)}>{periodOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><button type="button" onClick={refresh} disabled={loading}>{loading ? 'Refreshing...' : '\u21bb Refresh'}</button></div></header>
    <div className="oi-context"><span><i className="oi-dot oi-green"/> Production intelligence <b>LIVE RECORDS</b> <span className="oi-context__phase">Financial intelligence <b>PHASE 2 PREVIEW</b></span></span><span>{data ? `Updated ${stamp(data.generated_at)} (UK)` : 'Waiting for production records'}</span></div>
    {error && data && <RefreshFailed message={error}/>}{!data && (loading ? <LoadingState>Loading operational intelligence...</LoadingState> : error ? <ErrorState message={error} onRetry={refresh}/> : null)}
    {data && <>
      <div className="oi-kpis"><Kpi title="Cost per Tonne" kind="cost" detail={<span>Target <Phase2FinancialMetric label="Weekly target cost" unit="/ t" compact/></span>}><Phase2FinancialMetric label="Cost per Tonne" unit="/ t"/></Kpi>
        <Kpi title="Actual Tonnes This Week" kind="truck" detail={data.weekly.comparison_percent == null ? 'Comparable history unavailable' : <span title={data.weekly.comparison_note}>{n(data.weekly.comparison_percent)}% vs comparable week</span>}><strong className="oi-kpi__value">{tonnes(data.weekly.actual_tonnes)}</strong></Kpi>
        <Kpi title="Weekly Tonnage Target" kind="target" detail={data.weekly.target_tonnes == null ? 'Set in Management' : `${pct(data.weekly.progress_percent)} complete`}><strong className="oi-kpi__value oi-kpi__value--target">{tonnes(data.weekly.actual_tonnes)} / {data.weekly.target_tonnes == null ? 'Not set' : tonnes(data.weekly.target_tonnes)}</strong><div className="oi-progress" role="img" aria-label={`Weekly target: ${pct(data.weekly.progress_percent)} complete`}><i style={{ width: `${Math.max(0, Math.min(100, data.weekly.progress_percent ?? 0))}%` }}/></div></Kpi>
        <Kpi title="Measured Output Gap" kind="loss" detail="Recoverability not yet assessed"><strong className="oi-kpi__value">{tonnes(data.output_gap.total_tonnes)}</strong></Kpi>
        <Kpi title="Week Elapsed" kind="clock" detail={`${n(data.weekly.elapsed_days)} days into production week`}><strong className="oi-kpi__value">{pct(data.weekly.elapsed_percent)}</strong></Kpi>
      </div>
      <p className="oi-scope">Tonnes &amp; target: week from {stamp(data.weekly.window.start)}. Losses &amp; downtime: {data.window.label}. {data.weekly.excluded_readings > 0 && `${data.weekly.excluded_readings} readings excluded: incomplete production data.`}</p>
      {data.data_issues.length > 0 && <p className="oi-caption" role="status">Some production inputs need review. Open the data notes below before interpreting the output gap.</p>}
      <CommercialPreview/>
      <div className="oi-insights"><Section title="Top 3 Production Loss Drivers" className="oi-drivers"><table aria-label="Top 3 Production Loss Drivers"><thead><tr><th>#</th><th>Line</th><th>Cause</th><th>Minutes</th><th>Est. tonnes lost</th><th>Est. cost impact</th></tr></thead><tbody>{data.loss_drivers.map((row, i) => <tr key={`${row.line}-${row.machine}-${row.cause}`}><td><span className={`oi-rank oi-rank--${i}`}>{i + 1}</span></td><td>{row.fault_ids.length ? <Link title="Open recorded fault" to={`/dashboard/engineering?line=${encodeURIComponent(row.line)}&fault=${row.fault_ids[0]}`}>{row.line}</Link> : row.line}</td><td>{row.cause}</td><td>{n(row.minutes)}</td><td>{row.estimated_tonnes == null ? <span title="Not reliably attributable by cause">{'\u2014'}</span> : tonnes(row.estimated_tonnes)}</td><td><Phase2FinancialMetric label={`${row.line} ${row.cause} cost impact`} compact/></td></tr>)}</tbody></table>{!data.loss_drivers.length && <p className="oi-empty">No recorded stop causes in this period.</p>}<p className="oi-caption">{data.ranking_method}</p></Section>
        <Section title="Improvement Priorities" className="oi-priorities">{data.loss_drivers.map((row, i) => <article className="oi-priority" key={`${row.line}-${row.cause}`}><span className={`oi-rank oi-rank--${i}`}>{i + 1}</span><div><h3>{row.line}: {row.cause}</h3><p>{n(row.minutes)} min {'\u00b7'} {row.events} recorded {row.events === 1 ? 'event' : 'events'}</p><p>{row.investigation}</p></div><div className="oi-benefit"><small>Potential financial benefit</small><Phase2FinancialMetric label={`${row.line} ${row.cause} potential benefit`} unit="/ week" compact/></div></article>)}{!data.loss_drivers.length && <p className="oi-empty">Priorities will appear when production-stop evidence is recorded.</p>}</Section><LossDetails data={data}/></div>
      <div className="oi-lower"><Section title="Weight Through Time / Material Flow" note="This production week" className="oi-flow"><div className="oi-flow__stages">{data.material_flow.map((stage, i) => <div className={`oi-stage ${stage.connected ? 'oi-stage--connected' : ''}`} key={stage.stage}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={i === 4 ? 'M2 6h13v12H2zM15 10h4l3 4v4h-7M5 18v3m13-3v3' : i === 0 ? 'M5 21V5l7-3 7 3v16M5 8h14M9 21v-6h6v6' : i === 1 ? 'M3 21V9l6 3V6l6 5V3h6v18H3M6 16h3m4 0h3' : 'M3 7l9-4 9 4v13l-9 3-9-3V7M3 7l9 4 9-4M12 11v12'}/></svg><h3>{stage.stage}</h3><strong>{stage.connected ? tonnes(stage.tonnes) : '\u2014'}</strong><small>{stage.connected ? 'Recorded packaging output' : 'Data not connected'}</small></div>)}</div></Section>
        <Section title="Line Profitability Snapshot" note="Latest completed hour" className="oi-lines"><table aria-label="Line Profitability Snapshot"><thead><tr><th>Line</th><th>Status</th><th>Last hour achievement</th><th>Cost per tonne</th><th>Top current issue</th><th>Pallets remaining</th></tr></thead><tbody>{data.lines.map(row => <tr key={row.name}><td><Link to={`/dashboard?line=${encodeURIComponent(row.name)}`}>{row.name}</Link></td><td><span className={`oi-status oi-status--${row.status}`}>{row.status_label}</span></td><td>{row.last_hour?.line.status === 'not_scheduled' ? 'Not scheduled' : row.last_hour?.line.output_vs_target_percent == null ? 'No reported figure' : pct(row.last_hour.line.output_vs_target_percent)}</td><td><Phase2FinancialMetric label={`${row.name} cost per tonne`} unit="/ t" compact/></td><td>{row.current_fault_id == null ? row.current_issue : <Link to={`/dashboard/engineering?line=${encodeURIComponent(row.name)}&fault=${row.current_fault_id}`}>{row.current_issue}</Link>}</td><td>{n(row.job?.remaining_pallets)}</td></tr>)}</tbody></table><p className="oi-caption">Latest recorded HMI state; not continuous machine telemetry. Achievement = produced / expected packs.</p></Section></div>
      <Section title="Planned vs Unplanned Downtime" note={data.window.label} className="oi-downtime"><div className="oi-downtime__body"><div className="oi-downtime__chart"><div className="oi-downtime__labels"><span><b>{formatMinutes(d!.planned_minutes)}</b> Planned ({total ? pct(d!.planned_minutes / total * 100) : '\u2014'})</span><span><b>{formatMinutes(d!.unplanned_minutes)}</b> Unplanned ({pct(d!.unplanned_percent)})</span></div><div className="oi-stop-bar" role="img" aria-label={`${formatMinutes(d!.planned_minutes)} planned and ${formatMinutes(d!.unplanned_minutes)} unplanned downtime`}><i style={{ width: `${total ? d!.planned_minutes / total * 100 : 0}%` }}/><b style={{ width: `${total ? d!.unplanned_minutes / total * 100 : 0}%` }}/></div><p className="oi-caption">{formatMinutes(d!.not_scheduled_minutes)} Not Scheduled {'\u2014'} excluded from downtime. Recorded stops only.</p></div><div className="oi-impact"><small>Estimated cost impact</small><Phase2FinancialMetric label="Downtime estimated cost impact"/></div><div className="oi-takeaway"><span aria-hidden="true">{'\u2600'}</span><div><small>Key takeaway</small><p>{d!.unplanned_percent == null ? 'No downtime recorded in the selected period.' : `Unplanned stops account for ${pct(d!.unplanned_percent)} of recorded downtime.`}</p></div></div></div></Section>
      <StopDetails data={data}/>
    </>}
  </div></FinancialIntelligenceProvider>
}
export function OperationalIntelligence() {
  const [period, setPeriod] = useState<DashboardWindow>('production_week')
  const [line, setLine] = useState('')
  const result = useProtectedData((token, signal) => getOperationalIntelligence(token, { window: period, production_line: line || null }, signal), JSON.stringify({ period, line }))
  const { isLoading, loadedAt, error, reload } = result
  useEffect(() => {
    if (isLoading) return
    const timer = window.setTimeout(() => { if (!document.hidden) reload() }, 30_000)
    return () => window.clearTimeout(timer)
  }, [isLoading, loadedAt, error, reload])
  useEffect(() => {
    const refreshVisible = () => { if (!document.hidden) reload() }
    document.addEventListener('visibilitychange', refreshVisible)
    window.addEventListener('online', refreshVisible)
    return () => { document.removeEventListener('visibilitychange', refreshVisible); window.removeEventListener('online', refreshVisible) }
  }, [reload])
  return <OperationalIntelligenceView data={result.data} error={result.error} loading={result.isLoading} refresh={result.reload} period={period} onPeriod={setPeriod} line={line} onLine={setLine}/>
}
