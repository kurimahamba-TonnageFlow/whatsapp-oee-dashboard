import type { LineTechConfig } from '../linetech'
import { useEffect, useState } from 'react'
import { formatDuration } from '../progress'
import type { PlannedDowntimeEvent } from '../types'

interface PlannedDowntimeScreenProps {
  configuredReasons?: LineTechConfig
  /** Reasons other than Changeover, which has its own action because it
   * also records the structured QC changeover. */
  reasons: string[]
  activeEvent: PlannedDowntimeEvent | null
  isSubmitting: boolean
  errorMessage: string | null
  onStart: (reason: string, component?: string) => void
  onEnd: () => void
  /** Legacy in-run changeover. Omitted in the End Run -> Changeover flow. */
  onStartChangeover?: () => void
  onCancel: () => void
}

export function PlannedDowntimeScreen({
  configuredReasons,
  reasons,
  activeEvent,
  isSubmitting,
  errorMessage,
  onStart,
  onEnd,
  onStartChangeover,
  onCancel,
}: PlannedDowntimeScreenProps) {
  const [chosen,setChosen] = useState('')
  const [component,setComponent] = useState('')
  const [confirmingEnd, setConfirmingEnd] = useState(false)
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    if (!activeEvent) return
    const interval = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(interval)
  }, [activeEvent])

  if (activeEvent) {
    const elapsedMinutes = (now.getTime() - new Date(activeEvent.started_at).getTime()) / 60000

    return (
      <div className="hmi-screen hmi-planned-downtime">
        <h1>Planned Downtime — {activeEvent.reason}{activeEvent.component ? ` / ${activeEvent.component}` : ''}</h1>
        <p className="hmi-planned-downtime__elapsed">Elapsed: {formatDuration(elapsedMinutes)}</p>
        <p>Started by {activeEvent.started_by}. Pulse is recording this stop.</p>

        {errorMessage && (
          <p className="hmi-inline-error" role="alert">
            {errorMessage}
          </p>
        )}

        {confirmingEnd ? (
          <div className="hmi-inline-warning" role="alert">
            <p>End planned downtime now?</p>
            <div className="hmi-form-actions">
              <button
                type="button"
                className="hmi-secondary-button"
                onClick={() => setConfirmingEnd(false)}
                disabled={isSubmitting}
              >
                Keep Going
              </button>
              <button
                type="button"
                className="hmi-primary-button"
                onClick={onEnd}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Ending…' : 'Yes, End Downtime'}
              </button>
            </div>
          </div>
        ) : (
          <div className="hmi-form-actions">
            <button
              type="button"
              className="hmi-primary-button"
              onClick={() => setConfirmingEnd(true)}
            >
              End Planned Downtime
            </button>
            <button type="button" className="hmi-secondary-button" onClick={onCancel}>
              Return to Active Run
            </button>
          </div>
        )}
      </div>
    )
  }

  if (configuredReasons?.enabled) {
    const items=configuredReasons.planned.filter(p=>p.active)
    const selected=items.find(p=>p.reason===chosen)
    return <div className="hmi-screen linetech-screen"><p className="linetech-eyebrow">PLANNED DOWNTIME</p><h1>{selected ? selected.reason : 'Select planned stop'}</h1>
      <div className="hmi-button-grid">{!selected ? items.map(p=><button key={p.reason} className="linetech-tile linetech-planned" disabled={isSubmitting} onClick={()=>{setChosen(p.reason);setComponent('')}}>{p.reason}</button>) : selected.components.map(c=><button key={c} className="linetech-tile" aria-pressed={component===c} disabled={isSubmitting} onClick={()=>setComponent(c)}>{c}</button>)}</div>
      {selected && <div className="linetech-confirm"><h2>{selected.reason}{component ? ` / ${component}` : ''}</h2><p>Start the stop timer now. Ending this timer does not record a passed quality or CCP check.</p><button className="hmi-primary-button" disabled={isSubmitting || (!!selected.components.length && !component)} onClick={()=>onStart(selected.reason,component||undefined)}>Confirm planned stop</button></div>}
      {errorMessage && <p role="alert">{errorMessage}</p>}
      <button className="hmi-secondary-button" disabled={isSubmitting} onClick={()=>selected?setChosen(''):onCancel()}>Back</button>
    </div>
  }
  return (
    <div className="hmi-screen hmi-planned-downtime">
      <h1>Planned Downtime</h1>
      <p>Select a reason to start planned downtime.</p>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-button-grid">
        {reasons.map((reason) => (
          <button
            key={reason}
            type="button"
            className="hmi-primary-button"
            onClick={() => onStart(reason)}
            disabled={isSubmitting}
          >
            {reason}
          </button>
        ))}
        {onStartChangeover && (
          <button
            type="button"
            className="hmi-primary-button"
            onClick={onStartChangeover}
            disabled={isSubmitting}
          >
            Start Changeover
          </button>
        )}
      </div>
      {!onStartChangeover && (
        <p className="hmi-field-help">
          Changing product? Use End Run, then choose Changeover - so the old and new product runs stay
          separate.
        </p>
      )}

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel}>
          Return to Active Run
        </button>
      </div>
    </div>
  )
}
