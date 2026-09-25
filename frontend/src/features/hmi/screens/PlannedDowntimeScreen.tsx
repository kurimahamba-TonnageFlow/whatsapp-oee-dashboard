import { useEffect, useState } from 'react'
import { formatDuration } from '../progress'
import type { PlannedDowntimeEvent } from '../types'

interface PlannedDowntimeScreenProps {
  /** Reasons other than Changeover, which has its own action because it
   * also records the structured QC changeover. */
  reasons: string[]
  activeEvent: PlannedDowntimeEvent | null
  isSubmitting: boolean
  errorMessage: string | null
  onStart: (reason: string) => void
  onEnd: () => void
  onStartChangeover: () => void
  onCancel: () => void
}

export function PlannedDowntimeScreen({
  reasons,
  activeEvent,
  isSubmitting,
  errorMessage,
  onStart,
  onEnd,
  onStartChangeover,
  onCancel,
}: PlannedDowntimeScreenProps) {
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
        <h1>Planned Downtime — {activeEvent.reason}</h1>
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
        <button
          type="button"
          className="hmi-primary-button"
          onClick={onStartChangeover}
          disabled={isSubmitting}
        >
          Start Changeover
        </button>
      </div>

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel}>
          Return to Active Run
        </button>
      </div>
    </div>
  )
}
