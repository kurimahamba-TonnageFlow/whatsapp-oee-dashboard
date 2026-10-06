import type { ReactNode } from 'react'
import { formatDateTime } from '../format'

interface PageHeaderProps {
  title: string
  subtitle: string
  /** ISO timestamp of the backend's generated_at. */
  updatedAt: string | null
  onRefresh: () => void
  isRefreshing: boolean
  /** Extra line under "Last updated" (e.g. latest recorded activity). */
  meta?: ReactNode
  /** Extra controls beside Refresh (e.g. a link to another workspace). */
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, updatedAt, onRefresh, isRefreshing, meta, actions }: PageHeaderProps) {
  return (
    <header className="pd-header">
      <div>
        <h1 className="pd-header__title">{title}</h1>
        <p className="pd-header__subtitle">{subtitle}</p>
      </div>
      <div className="pd-header__side" aria-live="polite">
        <span>
          Last updated: <strong>{updatedAt ? formatDateTime(updatedAt) : '—'}</strong>
        </span>
        {meta && <span className="pd-muted">{meta}</span>}
        <div className="pd-header__actions">
          {actions}
          <button type="button" className="pd-button" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing && updatedAt ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
    </header>
  )
}
