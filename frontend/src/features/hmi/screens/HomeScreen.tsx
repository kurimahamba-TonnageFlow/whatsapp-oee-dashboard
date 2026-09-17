import { useEffect, useState } from 'react'
import type { HmiConfigLine } from '../../../types/api'
import { formatUkDateTime, resolveCurrentShift } from '../shift'
import { StatusPill } from '../components/StatusPill'
import type { ActiveRunRecord } from '../types'

export type HmiConfigState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; lines: HmiConfigLine[] }

interface HomeScreenProps {
  configState: HmiConfigState
  activeRun: ActiveRunRecord | null
  onRetry: () => void
  onStartRun: (lineName: string) => void
  onResumeActiveRun: () => void
  onEngineering: () => void
  onManagement: () => void
}

export function HomeScreen({
  configState,
  activeRun,
  onRetry,
  onStartRun,
  onResumeActiveRun,
  onEngineering,
  onManagement,
}: HomeScreenProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(interval)
  }, [])

  const shift = resolveCurrentShift(now)

  return (
    <div className="hmi-screen hmi-home">
      <header className="hmi-home__header">
        <p className="hmi-home__brand">TonnageFlow Pulse</p>
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

        {configState.status === 'ready' && configState.lines.length === 0 && (
          <p className="hmi-home__status-message">
            No production lines are configured yet. Ask a manager to add one.
          </p>
        )}

        {configState.status === 'ready' && configState.lines.length > 0 && (
          <div className="hmi-home__line-grid">
            {configState.lines.map((line) => {
              const isActiveHere = activeRun?.form.productionLine === line.name
              return (
                <article key={line.id} className="hmi-line-card">
                  <h2>{line.name}</h2>
                  {isActiveHere ? (
                    <StatusPill tone="blue">Active on this device</StatusPill>
                  ) : (
                    <StatusPill tone="green">Available</StatusPill>
                  )}
                  {isActiveHere ? (
                    <button type="button" onClick={onResumeActiveRun}>
                      Resume Run
                    </button>
                  ) : (
                    <button type="button" onClick={() => onStartRun(line.name)}>
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
