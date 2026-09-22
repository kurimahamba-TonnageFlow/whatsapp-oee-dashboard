interface ConfirmDialogProps {
  title: string
  message: string
  confirmLabel: string
  isBusy?: boolean
  variant?: 'default' | 'danger'
  onConfirm: () => void
  onCancel: () => void
}

/** A simple, always-visible-when-rendered confirmation step - used
 * before Accept Job and before Close Fault, so neither action can
 * happen from a single accidental tap. */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  isBusy = false,
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div className="engineering-confirm-overlay" role="presentation">
      <div className="engineering-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="engineering-confirm-title">
        <h2 id="engineering-confirm-title">{title}</h2>
        <p>{message}</p>
        <div className="engineering-confirm-dialog__actions">
          <button
            type="button"
            className="engineering-secondary-button"
            onClick={onCancel}
            disabled={isBusy}
          >
            Cancel
          </button>
          <button
            type="button"
            className={variant === 'danger' ? 'engineering-danger-button' : 'engineering-primary-button'}
            onClick={onConfirm}
            disabled={isBusy}
          >
            {isBusy ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
