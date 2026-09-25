import type { ReactNode } from 'react'

export type StatusTone = 'green' | 'amber' | 'red' | 'blue' | 'grey'

interface StatusPillProps {
  tone: StatusTone
  children: ReactNode
}

/** Consistent status colour: green = on target/successful, amber = at
 * risk/attention needed, red = stopped/fault/materially behind,
 * blue = neutral action or planned activity, grey = state not known
 * yet (never "everything is fine"). */
export function StatusPill({ tone, children }: StatusPillProps) {
  return <span className={`hmi-status-pill hmi-status-pill--${tone}`}>{children}</span>
}
