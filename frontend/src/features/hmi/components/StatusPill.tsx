import type { ReactNode } from 'react'

export type StatusTone = 'green' | 'amber' | 'red' | 'blue'

interface StatusPillProps {
  tone: StatusTone
  children: ReactNode
}

/** Consistent status colour: green = on target/successful, amber = at
 * risk/attention needed, red = stopped/fault/materially behind,
 * blue = neutral action or planned activity. */
export function StatusPill({ tone, children }: StatusPillProps) {
  return <span className={`hmi-status-pill hmi-status-pill--${tone}`}>{children}</span>
}
