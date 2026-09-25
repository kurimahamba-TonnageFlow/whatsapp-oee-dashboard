import { useEffect, useRef, useState } from 'react'
import { ConfirmDialog } from './ConfirmDialog'
import { HandoverForm } from './HandoverForm'
import { RepairUpdateForm } from './RepairUpdateForm'
import { HANDOVER_ACTION_TEXT, canHandOverFault, engineeringStatusLabel } from './constants'
import { formatDuration, formatTimestamp } from './format'
import type { CloseFaultPayload, EngineeringFault, RepairUpdatePayload } from './types'

interface FaultDetailPanelProps {
  fault: EngineeringFault
  currentEngineer: string
  onClose: () => void
  onRequestAccept: () => void
  isAccepting: boolean
  isSubmittingUpdate: boolean
  updateError: string | null
  updateSuccessMessage: string | null
  updateResetSignal: number
  onSubmitUpdate: (payload: RepairUpdatePayload) => void
  isSubmittingClose: boolean
  closeError: string | null
  onConfirmClose: (payload: CloseFaultPayload) => void
  isSubmittingHandover: boolean
  handoverError: string | null
  onConfirmHandover: (note: string) => void
}

/** At most one of Close or Handover can be pending confirmation at
 * once - a tagged union (rather than two separate useState calls)
 * makes that structurally impossible, so their two ConfirmDialogs can
 * never both render at the same time. */
type PendingAction = { type: 'close'; payload: CloseFaultPayload } | { type: 'handover'; note: string } | null

export function FaultDetailPanel({
  fault,
  currentEngineer,
  onClose,
  onRequestAccept,
  isAccepting,
  isSubmittingUpdate,
  updateError,
  updateSuccessMessage,
  updateResetSignal,
  onSubmitUpdate,
  isSubmittingClose,
  closeError,
  onConfirmClose,
  isSubmittingHandover,
  handoverError,
  onConfirmHandover,
}: FaultDetailPanelProps) {
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [isHandoverFormOpen, setIsHandoverFormOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // While the panel is open the page behind it must not scroll, and
  // focus must stay inside. Escape closes it only when no confirmation
  // is pending - a half-answered "are you sure?" should be dismissed
  // first, by its own dialog.
  const isConfirming = pendingAction !== null

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'

    panelRef.current?.focus()

    return () => {
      document.body.style.overflow = overflow
      // Return focus to whatever opened the panel, if it still exists.
      if (opener && document.contains(opener)) opener.focus()
    }
  }, [])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isConfirming) {
        event.stopPropagation()
        onClose()
        return
      }

      if (event.key !== 'Tab') return

      const panel = panelRef.current
      if (!panel) return

      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null)

      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isConfirming, onClose])

  const isOpen = fault.production_status === 'Ongoing'
  const isMine = fault.engineer === currentEngineer
  const isUnassigned = fault.engineer === null
  const canHandOver = canHandOverFault(fault, currentEngineer)

  return (
    <div className="engineering-detail-overlay" role="presentation">
      <div
        className="engineering-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="engineering-detail-title"
        ref={panelRef}
        tabIndex={-1}
      >
        {/* Stays put while the body scrolls, so the engineer can always
            see which fault they are working on and how to get out. */}
        <div className="engineering-detail-panel__header">
          <h2 id="engineering-detail-title">
            {fault.machine} — {fault.reason}
          </h2>
          <button type="button" className="engineering-secondary-button" onClick={onClose}>
            Close panel
          </button>
        </div>

        <div className="engineering-detail-panel__body">
        <dl className="engineering-detail-panel__summary">
          <div>
            <dt>Production line</dt>
            <dd>{fault.production_line}</dd>
          </div>
          <div>
            <dt>Reported by</dt>
            <dd>{fault.reported_by}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{formatTimestamp(fault.opened_at)}</dd>
          </div>
          <div>
            <dt>Elapsed</dt>
            <dd>{formatDuration(fault.duration_minutes)}</dd>
          </div>
          <div>
            <dt>Production status</dt>
            <dd>{fault.production_status}</dd>
          </div>
          <div>
            <dt>Engineering status</dt>
            <dd>{engineeringStatusLabel(fault.engineering_status)}</dd>
          </div>
          <div>
            <dt>Assigned engineer</dt>
            <dd>{fault.engineer ?? 'Unassigned'}</dd>
          </div>
          {fault.accepted_at && (
            <div>
              <dt>Accepted</dt>
              <dd>{formatTimestamp(fault.accepted_at)}</dd>
            </div>
          )}
          {fault.resolved_at && (
            <div>
              <dt>Resolved</dt>
              <dd>{formatTimestamp(fault.resolved_at)}</dd>
            </div>
          )}
        </dl>

        {isOpen && isUnassigned && (
          <button type="button" className="engineering-primary-button" onClick={onRequestAccept} disabled={isAccepting}>
            {isAccepting ? 'Accepting…' : 'Accept Job'}
          </button>
        )}

        {isOpen && !isUnassigned && !isMine && (
          <p className="engineering-inline-note">
            This job is assigned to {fault.engineer}. Only they can add updates, hand it over, or close it.
          </p>
        )}

        {canHandOver && (
          <section className="engineering-handover">
            <h3>Hand Over Job</h3>
            <p className="engineering-inline-note">Release this job so another engineer can accept it.</p>
            {handoverError && (
              <p className="engineering-inline-error" role="alert">
                {handoverError}
              </p>
            )}
            {isHandoverFormOpen ? (
              <>
                <HandoverForm
                  isSubmitting={isSubmittingHandover}
                  onSubmit={(note) => setPendingAction({ type: 'handover', note })}
                />
                <button
                  type="button"
                  className="engineering-secondary-button"
                  onClick={() => setIsHandoverFormOpen(false)}
                  disabled={isSubmittingHandover}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                className="engineering-secondary-button"
                onClick={() => setIsHandoverFormOpen(true)}
              >
                Hand Over Job
              </button>
            )}
          </section>
        )}

        <section className="engineering-repair-history" aria-label="Repair-update history">
          <h3>Repair-update history</h3>
          {fault.repair_updates.length === 0 ? (
            <p className="engineering-empty-state">No repair updates recorded yet.</p>
          ) : (
            <ul>
              {fault.repair_updates.map((update) => {
                // A genuine handover is identified by the exact, fixed
                // `action` text the /handover endpoint always writes
                // (HANDOVER_ACTION_TEXT) - NOT by repair_classification
                // being NULL, since an ordinary unclassified Follow Up
                // update can also have no classification. This is a
                // plain string match against a field the API already
                // returns; no database column or migration involved.
                const isHandoverEntry = update.update_type === 'Follow Up' && update.action === HANDOVER_ACTION_TEXT

                return (
                  <li key={update.id} className="engineering-repair-history__entry">
                    <div className="engineering-repair-history__meta">
                      <strong>{update.engineer ?? 'Unknown engineer'}</strong>
                      <span>{formatTimestamp(update.created_at)}</span>
                      {isHandoverEntry ? <span>Handed over</span> : update.repair_classification && <span>{update.repair_classification}</span>}
                    </div>
                    {isHandoverEntry ? (
                      update.finding && <p>Handover note: {update.finding}</p>
                    ) : (
                      <>
                        {update.finding && <p>Finding: {update.finding}</p>}
                        {update.action && <p>Action: {update.action}</p>}
                      </>
                    )}
                    {update.notes && <p>Notes: {update.notes}</p>}
                    {update.repair_classification === 'Machine Setting' && (
                      <ul className="engineering-repair-history__setting-detail">
                        <li>Setting: {update.setting_name}</li>
                        <li>Previous value: {update.previous_value}</li>
                        <li>New value: {update.new_value}</li>
                        <li>Reason for change: {update.reason_for_change}</li>
                        <li>Affected products/formats: {update.affected_products_or_formats}</li>
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {isOpen && isMine && (
          <>
            <section className="engineering-add-update">
              <h3>Add Repair Update</h3>
              {updateSuccessMessage && (
                <p className="engineering-success-note" role="status">
                  {updateSuccessMessage}
                </p>
              )}
              {updateError && (
                <p className="engineering-inline-error" role="alert">
                  {updateError}
                </p>
              )}
              <RepairUpdateForm
                mode="update"
                isSubmitting={isSubmittingUpdate}
                onSubmit={onSubmitUpdate}
                resetSignal={updateResetSignal}
              />
            </section>

            <section className="engineering-close-fault">
              <h3>Close Fault</h3>
              <p className="engineering-inline-note">
                Closing marks both Engineering status and Production status as Resolved. This cannot be
                undone from this screen.
              </p>
              {closeError && (
                <p className="engineering-inline-error" role="alert">
                  {closeError}
                </p>
              )}
              <RepairUpdateForm
                mode="close"
                isSubmitting={isSubmittingClose}
                onSubmit={(payload) =>
                  setPendingAction({ type: 'close', payload: payload as CloseFaultPayload })
                }
              />
            </section>
          </>
        )}
        </div>
      </div>

      {pendingAction?.type === 'close' && (
        <ConfirmDialog
          title="Close this fault?"
          message="This will mark Engineering status and Production status as Resolved for this fault. This cannot be undone from this screen."
          confirmLabel="Close Fault"
          variant="danger"
          isBusy={isSubmittingClose}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => {
            onConfirmClose(pendingAction.payload)
            setPendingAction(null)
          }}
        />
      )}

      {pendingAction?.type === 'handover' && (
        <ConfirmDialog
          title="Hand over this job?"
          message="This job will become unassigned and return to Open Production Faults."
          confirmLabel="Hand Over Job"
          isBusy={isSubmittingHandover}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => {
            onConfirmHandover(pendingAction.note)
            setPendingAction(null)
            setIsHandoverFormOpen(false)
          }}
        />
      )}
    </div>
  )
}
