import { useEffect, useState } from 'react'
import type { PlannedDowntimeEvent } from '../awaitingApiIntegration'
import { formatDuration } from '../progress'

interface PlannedDowntimeScreenProps {
  reasons: string[]
  activeEvent: PlannedDowntimeEvent | null
  isSubmitting: boolean
  onStart: (reason: string) => void
  onEnd: () => void
  onCancel: () => void
}

export function PlannedDowntimeScreen({
  reasons,
  activeEvent,
  isSubmitting,
  onStart,
  onEnd,
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
    const elapsedMinutes =
      (now.getTime() - new Date(activeEvent.startedAtIso).getTime()) / 60000

    return (
      <div className="hmi-screen hmi-planned-downtime">
        <h1>Planned Downtime — {activeEvent.reason}</h1>
        <p className="hmi-planned-downtime__elapsed">
          Elapsed: {formatDuration(elapsedMinutes)}
        </p>

        {confirmingEnd ? (
          <div className="hmi-inline-error" role="alert">
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
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="hmi-screen hmi-planned-downtime">
      <h1>Planned Downtime</h1>
      <p>Select a reason to start planned downtime.</p>

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
      </div>

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onCancel}>
          Return to Active Run
        </button>
      </div>
    </div>
  )
}
