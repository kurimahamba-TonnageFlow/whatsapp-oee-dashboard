import type { StatusTone } from './StatusPill'

interface ProgressBarProps {
  percentComplete: number
  tone: StatusTone
  label: string
}

export function ProgressBar({ percentComplete, tone, label }: ProgressBarProps) {
  const clamped = Math.min(Math.max(percentComplete, 0), 100)

  return (
    <div className="hmi-progress" aria-label={label}>
      <div
        className="hmi-progress__track"
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`hmi-progress__fill hmi-progress__fill--${tone}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="hmi-progress__value">{Math.round(clamped)}%</span>
    </div>
  )
}
