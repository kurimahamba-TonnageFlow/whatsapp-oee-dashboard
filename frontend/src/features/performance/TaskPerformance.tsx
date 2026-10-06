import { useState } from 'react'
import { apiClient } from '../../api/client'
import { useProtectedData } from '../management/session/useProtectedData'
import { ErrorState, RefreshFailed } from '../dashboard/ui/states'

interface Cell {
  technician: string; task: string; rating: 'grey'; status: string; recorded_count: number;
  groups: {configuration: string; completed_count: number; median_minutes: number; fastest_minutes: number; slowest_minutes: number}[];
  evidence: {id: string; benchmark_exclusions?: string[]; notes?: string; waiting_minutes?: number | null; shared_work?: boolean | null; source?: string; started_at: string; ended_at: string | null; started_by: string; ended_by: string | null; elapsed_minutes: number | null; configuration: string}[];
}
interface Report {tasks: string[]; technicians: string[]; cells: Cell[]; unclassified_count: number; since: string; until: string}
const time = (value: string) => new Date(value).toLocaleString('en-GB', {timeZone: 'Europe/London'})

export function TaskPerformance() {
  const report = useProtectedData((token, signal) => apiClient.get<Report>('/api/v1/management/task-performance', {token, signal}), 'rovema-task-performance')
  const [selected, setSelected] = useState<{technician: string; task: string} | null>(null)
  const cell = report.data?.cells.find(c => c.technician === selected?.technician && c.task === selected?.task)
  return <section className="pulse-panel" aria-labelledby="task-performance-heading">
    <h2 id="task-performance-heading">Rovema task performance</h2>
    <p>Recorded task timing, not a skills assessment. Separate scope: last 90 days, all Rovema technicians. The run filters above do not apply.</p>
    <p>Grey means gathering evidence. Reference times, minimum samples and colour thresholds have not been agreed. Managers cannot assign colours.</p>
    <p>New task observations name the reported performer and record waiting/shared work. Legacy timers identify their reporter only and are excluded from benchmarks. Elapsed time may include unreported delays. Faster CCP checks do not demonstrate safe or competent checks.</p>
    <button type="button" onClick={report.reload} disabled={report.isLoading}>Refresh task evidence</button>
    {report.error && (report.data ? <RefreshFailed message={report.error} /> : <ErrorState message={report.error} onRetry={report.reload} />)}
    {!report.data && report.isLoading && <p>Loading task evidence?</p>}
    {report.data && <>
      <p>{time(report.data.since)} to {time(report.data.until)} (Europe/London). Task starts within this window.</p>
      <p>{report.data.unclassified_count} records have no exact task classification and are excluded. Use Record task on the tablet for all seven tasks, including Casepacker, Robot and changeovers. Other operational timers do not become task observations automatically.</p>
      <div style={{overflowX: 'auto'}}><table className="pd-table"><caption>Grey cells show the number of recorded timers. Select a cell to inspect evidence.</caption>
        <thead><tr><th scope="col">Task / technician</th>{report.data.technicians.map(name => <th scope="col" key={name}>{name}</th>)}</tr></thead>
        <tbody>{report.data.tasks.map(task => <tr key={task}><th scope="row">{task}</th>{report.data!.technicians.map(name => {
          const current = report.data!.cells.find(c => c.task === task && c.technician === name)
          return <td key={name}><button type="button" className="pulse-status pulse-status--neutral" aria-label={`${name}, ${task}: grey, ${current?.recorded_count ?? 0} timers`} onClick={() => setSelected({technician: name, task})}>Grey ? {current?.recorded_count ?? 0}</button></td>
        })}</tr>)}</tbody></table></div>
      <section aria-label="Benchmarking tracker"><h3>Benchmarking tracker ? observed times</h3>
        <p>For later review only. Fastest and slowest are completed timer observations, not targets. Open, zero-duration, incomplete, shared-work and waiting-affected records are excluded. One observation will have identical fastest and slowest times.</p>
        {report.data.cells.every(c => c.groups.length === 0) ? <p>No completed task timers available for benchmarking yet.</p> :
          <div style={{overflowX: 'auto'}}><table className="pd-table"><thead><tr><th scope="col">Reported by</th><th scope="col">Task</th><th scope="col">Product / from configuration / to configuration</th><th scope="col">Completed</th><th scope="col">Fastest (min)</th><th scope="col">Median (min)</th><th scope="col">Slowest (min)</th></tr></thead>
            <tbody>{report.data.cells.flatMap(c => c.groups.map(g => <tr key={`${c.technician}-${c.task}-${g.configuration}`}><td>{c.technician}</td><td>{c.task}</td><td>{g.configuration}</td><td>{g.completed_count}</td><td>{g.fastest_minutes}</td><td>{g.median_minutes}</td><td>{g.slowest_minutes}</td></tr>))}</tbody>
          </table></div>}
      </section>
      {cell && <section aria-label="Selected task evidence"><h3>{cell.technician} ? {cell.task}</h3><p>{cell.status}</p>
        {cell.groups.map(group => <p key={group.configuration}>{group.configuration}: {group.completed_count} completed timers; median {group.median_minutes} minutes. Same reported product and start/end configuration only; other conditions may differ.</p>)}
        {cell.evidence.length === 0 ? <p>No timed evidence recorded for this task.</p> : <ul>{cell.evidence.map(e => <li key={e.id}>Timer #{e.id}: {time(e.started_at)} to {e.ended_at ? time(e.ended_at) : 'Still open'}; {e.elapsed_minutes === null ? 'No completed duration' : `${e.elapsed_minutes} elapsed minutes`}. Started by {e.started_by}; ended by {e.ended_by ?? 'not recorded'}. {e.configuration}. {e.benchmark_exclusions?.length ? `Excluded from benchmarks: ${e.benchmark_exclusions.join("; ")}.` : "Eligible completed observation."} {e.notes && `Context: ${e.notes}`} {e.waiting_minutes != null && `Waiting: ${e.waiting_minutes} min.`}</li>)}</ul>}
      </section>}
    </>}
  </section>
}
