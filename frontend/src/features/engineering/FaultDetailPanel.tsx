import { useState } from 'react'
import { ConfirmDialog } from './ConfirmDialog'
import { HandoverForm } from './HandoverForm'
import { RepairUpdateForm } from './RepairUpdateForm'
import { HANDOVER_ACTION_TEXT, canHandOverFault, engineeringStatusLabel } from './constants'
import { formatDuration, formatTimestamp } from './format'
import type { EngineeringFault, RepairUpdatePayload } from './types'

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
  onConfirmClose: (payload: RepairUpdatePayload) => void
  isSubmittingHandover: boolean
  handoverError: string | null
  onConfirmHandover: (note: string) => void
}

/** At most one of Close or Handover can be pending confirmation at
 * once - a tagged union (rather than two separate useState calls)
 * makes that structurally impossible, so their two ConfirmDialogs can
 * never both render at the same time. */
type PendingAction = { type: 'close'; payload: RepairUpdatePayload } | { type: 'handover'; note: string } | null

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
      >
        <div className="engineering-detail-panel__header">
          <h2 id="engineering-detail-title">
            {fault.machine} — {fault.reason}
          </h2>
          <button type="button" className="engineering-secondary-button" onClick={onClose}>
            Close panel
          </button>
        </div>

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
                onSubmit={(payload) => setPendingAction({ type: 'close', payload })}
              />
            </section>
          </>
        )}
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
