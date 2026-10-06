import type { ReactNode } from 'react'
import type { Tone } from './MetricCard'

/** Status pill. The text always carries the meaning; colour only reinforces it. */
export function StatusBadge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`pd-badge pd-badge--${tone}`}>{children}</span>
}
