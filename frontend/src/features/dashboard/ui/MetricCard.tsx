import { useId, type ReactNode } from 'react'

export type Tone = 'good' | 'bad' | 'warn' | 'neutral'

interface MetricCardProps {
  label: string
  value?: ReactNode
  detail?: ReactNode
  /** Colours the value. Only for real status (on target / behind / warning). */
  tone?: Tone
  /** Decorative glyph. */
  icon?: string
  /** Shown instead of a value: why this metric has no live data yet. */
  unavailable?: string
}

/** One KPI tile. The label is an h3 so each card is a named region. */
export function MetricCard({ label, value, detail, tone, icon, unavailable }: MetricCardProps) {
  const labelId = useId()
  return (
    <article className={`pd-metric${unavailable ? ' pd-metric--unavailable' : ''}`} aria-labelledby={labelId}>
      {icon && (
        <span className="pd-metric__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <div className="pd-metric__body">
        <h3 id={labelId} className="pd-metric__label">
          {label}
        </h3>
        {unavailable ? (
          <>
            <p className="pd-metric__value pd-metric__value--na">Data not available yet</p>
            <p className="pd-metric__detail">{unavailable}</p>
          </>
        ) : (
          <>
            <p className={`pd-metric__value${tone ? ` pd-tone--${tone}` : ''}`}>{value}</p>
            {detail && <p className="pd-metric__detail">{detail}</p>}
          </>
        )}
      </div>
    </article>
  )
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="pd-metrics">{children}</div>
}
