import type { ReactNode } from 'react'

export function LoadingState({ children }: { children: ReactNode }) {
  return (
    <p className="pd-state" role="status">
      <span className="pd-state__spinner" aria-hidden="true" />
      {children}
    </p>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="pd-state pd-state--error" role="alert">
      <p>{message}</p>
      <button type="button" className="pd-button" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}

export function EmptyState({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="pd-state pd-state--empty">
      {title && <h3 className="pd-state__title">{title}</h3>}
      <p>{children}</p>
    </div>
  )
}

/** Missing features are explained in user terms; implementation notes stay in source. */
export function NotAvailable({ children }: { children: ReactNode; needed?: string }) {
  return (
    <div className="pd-na" role="note">
      <p className="pd-na__title">Data not available yet</p>
      <p>{children}</p>
    </div>
  )
}

/** A refresh failed but older figures are still on screen. */
export function RefreshFailed({ message }: { message: string }) {
  return (
    <p className="pd-alert" role="alert">
      Could not refresh: {message} The figures below are from the last successful load.
    </p>
  )
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="pd-notice" role="note">
      {children}
    </p>
  )
}
