import { useId, type ReactNode } from 'react'

interface PanelProps {
  title: string
  children: ReactNode
  /** Right-aligned controls in the panel header (tabs, links). */
  actions?: ReactNode
  /** Extra class for grid placement. */
  className?: string
}

/** The shared dashboard card: a titled section with the green accent bar. */
export function Panel({ title, children, actions, className }: PanelProps) {
  const headingId = useId()
  return (
    <section className={`pd-panel${className ? ` ${className}` : ''}`} aria-labelledby={headingId}>
      <header className="pd-panel__header">
        <h2 id={headingId} className="pd-panel__title">
          {title}
        </h2>
        {actions && <div className="pd-panel__actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}
