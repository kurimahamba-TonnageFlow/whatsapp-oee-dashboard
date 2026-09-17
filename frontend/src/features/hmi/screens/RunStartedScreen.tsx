import { useEffect } from 'react'
import type { StartRunFormValues } from '../types'

interface RunStartedScreenProps {
  values: StartRunFormValues
  onContinue: () => void
}

const AUTO_CONTINUE_MS = 1600

/** Shown for ~1-2 seconds after a confirmed Start Run, then moves on
 * to the Active Run screen automatically. */
export function RunStartedScreen({ values, onContinue }: RunStartedScreenProps) {
  useEffect(() => {
    const timer = setTimeout(onContinue, AUTO_CONTINUE_MS)
    return () => clearTimeout(timer)
  }, [onContinue])

  return (
    <div className="hmi-screen hmi-run-started" role="status">
      <p className="hmi-run-started__mark">✓ RUN STARTED</p>
      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>Technician</dt>
          <dd>{values.lineTechnician}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Target speed</dt>
          <dd>{values.targetSpeedPpm} packs/min</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pallets remaining</dt>
          <dd>{values.palletsRemaining}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Shift</dt>
          <dd>{values.shift}</dd>
        </div>
      </dl>
    </div>
  )
}
