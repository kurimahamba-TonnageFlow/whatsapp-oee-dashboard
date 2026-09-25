import { useEffect, useState } from 'react'
import type { HmiConfigLine } from '../../../types/api'
import { formatUkDateTime, resolveCurrentShift } from '../shift'
import { StatusPill } from '../components/StatusPill'
import type { LineStateStatus } from '../useLineStatePolling'
import type { HmiLineState, StoredActiveRun } from '../types'

export type HmiConfigState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; lines: HmiConfigLine[] }

interface HomeScreenProps {
  configState: HmiConfigState
  lineState: LineStateStatus
  activeRun: StoredActiveRun | null
  isRestoring?: boolean
  /** The line currently being opened, so only its own button is busy. */
  openingLine?: string | null
  onRetry: () => void
  onRetryLineState: () => void
  onStartRun: (lineName: string) => void
  onOpenActiveRun: (runId: number, lineName: string) => void
  onEngineering: () => void
  onManagement: () => void
}

function activityLabel(line: HmiLineState) {
  if (line.stale_status === 'stale') {
    return line.stale_reason ?? 'No recent update.'
  }
  if (line.minutes_since_last_hourly_update === null) {
    return 'No hourly update recorded yet.'
  }
  return `Last update ${line.minutes_since_last_hourly_update} min ago.`
}

export function HomeScreen({
  configState,
  lineState,
  activeRun,
  isRestoring = false,
  openingLine = null,
  onRetry,
  onRetryLineState,
  onStartRun,
  onOpenActiveRun,
  onEngineering,
  onManagement,
}: HomeScreenProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(interval)
  }, [])

  const shift = resolveCurrentShift(now)

  const stateByLine = new Map<string, HmiLineState>(
    lineState.status === 'ready' ? lineState.lines.map((line) => [line.production_line, line]) : [],
  )

  return (
    <div className="hmi-screen hmi-home">
      <header className="hmi-home__header">
        <p className="hmi-home__brand">Tonnage Flow Pulse</p>
        <p className="hmi-home__clock">{formatUkDateTime(now)}</p>
        <p className="hmi-home__shift">Current shift: {shift.label}</p>
      </header>

      <section aria-labelledby="hmi-home-lines-heading" className="hmi-home__lines">
        <h1 id="hmi-home-lines-heading">Select a production line</h1>

        {configState.status === 'loading' && (
          <p className="hmi-home__status-message">Loading production lines…</p>
        )}

        {configState.status === 'error' && (
          <div className="hmi-home__status-message hmi-home__status-message--error">
            <p>Could not load production lines. Check the connection and try again.</p>
            <button type="button" onClick={onRetry}>
              Retry
            </button>
          </div>
        )}

        {configState.status === 'ready' && lineState.status === 'error' && (
          <div className="hmi-home__status-message hmi-home__status-message--error" role="alert">
            <p>
              Line status is unavailable, so Pulse cannot confirm which lines are already
              running. Do not start a run until this is working again.
            </p>
            <button type="button" onClick={onRetryLineState}>
              Retry line status
            </button>
          </div>
        )}

        {configState.status === 'ready' && configState.lines.length === 0 && (
          <p className="hmi-home__status-message">
            No production lines are configured yet. Ask a manager to add one.
          </p>
        )}

        {configState.status === 'ready' && configState.lines.length > 0 && (
          <div className="hmi-home__line-grid">
            {configState.lines.map((line) => {
              const state = stateByLine.get(line.name)
              const isKnown = lineState.status === 'ready' && state !== undefined
              const isActive = isKnown && state.has_active_run
              // What this device remembers starting - used only for
              // wording, never to decide whether the line is free.
              const startedHere = activeRun?.productionLine === line.name
              const isOpening = openingLine === line.name

              return (
                <article key={line.id} className="hmi-line-card">
                  <h2>{line.name}</h2>

                  {lineState.status === 'loading' && (
                    <StatusPill tone="grey">Checking status…</StatusPill>
                  )}

                  {lineState.status === 'error' && (
                    <StatusPill tone="grey">Status unavailable</StatusPill>
                  )}

                  {isKnown && !isActive && <StatusPill tone="green">Available</StatusPill>}

                  {isActive && (
                    <>
                      <StatusPill tone="blue">Run Active</StatusPill>
                      <p className="hmi-line-card__detail">
                        {startedHere ? 'Started on this device.' : 'Started on another device.'}
                      </p>
                      <p className="hmi-line-card__detail">
                        {state.line_technician} · {state.shift} · {state.customer} — {state.product}
                      </p>
                      {state.planned_downtime_active && (
                        <StatusPill tone="amber">Planned downtime</StatusPill>
                      )}
                      {state.changeover_active && <StatusPill tone="amber">Changeover</StatusPill>}
                      {state.engineering_fault_open && (
                        <StatusPill tone="red">
                          {state.open_fault_count === 1
                            ? 'Engineering fault open'
                            : `${state.open_fault_count} engineering faults open`}
                        </StatusPill>
                      )}
                      {state.stale_status === 'stale' && (
                        <StatusPill tone="amber">Needs an update</StatusPill>
                      )}
                      <p className="hmi-line-card__detail">{activityLabel(state)}</p>
                    </>
                  )}

                  {isActive ? (
                    <button
                      type="button"
                      onClick={() => onOpenActiveRun(state.run_id as number, line.name)}
                      disabled={isRestoring || isOpening}
                    >
                      {isOpening ? 'Opening…' : 'Open Active Run'}
                    </button>
                  ) : (
                    <button type="button" onClick={() => onStartRun(line.name)} disabled={!isKnown}>
                      Start Run
                    </button>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </section>

      <footer className="hmi-home__footer">
        <button type="button" className="hmi-secondary-button" onClick={onEngineering}>
          Engineering
        </button>
        <button type="button" className="hmi-secondary-button" onClick={onManagement}>
          Management
        </button>
      </footer>
    </div>
  )
}
