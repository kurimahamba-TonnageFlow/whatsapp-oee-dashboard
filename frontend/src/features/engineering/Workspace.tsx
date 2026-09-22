import { useMemo, useState } from 'react'
import * as engineeringApi from './api'
import { ApiRequestError } from '../../api/client'
import { ConfirmDialog } from './ConfirmDialog'
import { FaultDetailPanel } from './FaultDetailPanel'
import { FaultList } from './FaultList'
import { useFaultPolling } from './useFaultPolling'
import type { EngineeringFault, RepairUpdatePayload } from './types'

type TabKey = 'open' | 'mine' | 'resolved'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'open', label: 'Open Production Faults' },
  { key: 'mine', label: 'My Engineering Jobs' },
  { key: 'resolved', label: 'Resolved Jobs' },
]

interface WorkspaceProps {
  token: string
  engineerName: string
  onLogout: () => void
  onSessionExpired: () => void
}

function safeActionError(error: unknown, fallback: string): string {
  return error instanceof ApiRequestError ? error.message : fallback
}

export function Workspace({ token, engineerName, onLogout, onSessionExpired }: WorkspaceProps) {
  const { faults, isLoading, isRefreshing, loadError, refreshError, lastRefreshedAt, refresh } =
    useFaultPolling(token, onSessionExpired)

  const [activeTab, setActiveTab] = useState<TabKey>('open')
  const [selectedFaultId, setSelectedFaultId] = useState<number | null>(null)

  const [pendingAcceptFault, setPendingAcceptFault] = useState<EngineeringFault | null>(null)
  const [isAccepting, setIsAccepting] = useState(false)
  const [acceptError, setAcceptError] = useState<string | null>(null)

  const [isSubmittingUpdate, setIsSubmittingUpdate] = useState(false)
  const [updateError, setUpdateError] = useState<string | null>(null)
  const [updateSuccessMessage, setUpdateSuccessMessage] = useState<string | null>(null)
  const [updateResetSignal, setUpdateResetSignal] = useState(0)

  const [isSubmittingClose, setIsSubmittingClose] = useState(false)
  const [closeError, setCloseError] = useState<string | null>(null)

  const [isSubmittingHandover, setIsSubmittingHandover] = useState(false)
  const [handoverError, setHandoverError] = useState<string | null>(null)
  const [handoverSuccessMessage, setHandoverSuccessMessage] = useState<string | null>(null)

  const openFaults = useMemo(() => faults.filter((f) => f.production_status === 'Ongoing'), [faults])
  const myFaults = useMemo(() => openFaults.filter((f) => f.engineer === engineerName), [openFaults, engineerName])
  const resolvedFaults = useMemo(() => faults.filter((f) => f.production_status === 'Resolved'), [faults])

  const selectedFault = faults.find((f) => f.downtime_event_id === selectedFaultId) ?? null

  function handleLogoutClick() {
    // Best-effort server-side revocation - the in-memory token is
    // cleared by onLogout() regardless of whether this call succeeds.
    engineeringApi.logout(token).catch(() => {})
    onLogout()
  }

  function requestAccept(fault: EngineeringFault) {
    setAcceptError(null)
    setPendingAcceptFault(fault)
  }

  function confirmAccept() {
    if (!pendingAcceptFault || isAccepting) return
    setIsAccepting(true)
    setAcceptError(null)

    engineeringApi
      .acceptFault(token, pendingAcceptFault.downtime_event_id)
      .then((response) => {
        setPendingAcceptFault(null)
        setSelectedFaultId(response.downtime_event_id)
        refresh()
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 401) {
          onSessionExpired()
          return
        }
        setAcceptError(safeActionError(error, 'Could not accept this job. Please try again.'))
      })
      .finally(() => setIsAccepting(false))
  }

  function handleSubmitUpdate(payload: RepairUpdatePayload) {
    if (!selectedFault || isSubmittingUpdate) return
    setIsSubmittingUpdate(true)
    setUpdateError(null)
    setUpdateSuccessMessage(null)

    engineeringApi
      .addRepairUpdate(token, selectedFault.downtime_event_id, payload)
      .then(() => {
        setUpdateSuccessMessage('Repair update saved.')
        setUpdateResetSignal((n) => n + 1)
        refresh()
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 401) {
          onSessionExpired()
          return
        }
        setUpdateError(safeActionError(error, 'Could not save this update. Please try again.'))
      })
      .finally(() => setIsSubmittingUpdate(false))
  }

  function handleConfirmClose(payload: RepairUpdatePayload) {
    if (!selectedFault || isSubmittingClose) return
    setIsSubmittingClose(true)
    setCloseError(null)

    engineeringApi
      .closeFault(token, selectedFault.downtime_event_id, payload)
      .then(() => {
        setSelectedFaultId(null)
        refresh()
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 401) {
          onSessionExpired()
          return
        }
        setCloseError(safeActionError(error, 'Could not close this fault. Please try again.'))
      })
      .finally(() => setIsSubmittingClose(false))
  }

  function handleConfirmHandover(note: string) {
    if (!selectedFault || isSubmittingHandover) return
    setIsSubmittingHandover(true)
    setHandoverError(null)
    setHandoverSuccessMessage(null)

    engineeringApi
      .handOverFault(token, selectedFault.downtime_event_id, { note })
      .then(() => {
        setSelectedFaultId(null)
        setActiveTab('open')
        setHandoverSuccessMessage('Job handed over. It is now unassigned in Open Production Faults.')
        refresh()
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 401) {
          onSessionExpired()
          return
        }
        setHandoverError(safeActionError(error, 'Could not hand over this job. Please try again.'))
      })
      .finally(() => setIsSubmittingHandover(false))
  }

  function closeDetailPanel() {
    setSelectedFaultId(null)
    setUpdateError(null)
    setUpdateSuccessMessage(null)
    setCloseError(null)
    setHandoverError(null)
  }

  const activeFaults = activeTab === 'open' ? openFaults : activeTab === 'mine' ? myFaults : resolvedFaults
  const emptyMessage =
    activeTab === 'open'
      ? 'No open production faults right now.'
      : activeTab === 'mine'
        ? 'No jobs are currently assigned to you.'
        : 'No resolved jobs yet.'

  return (
    <div className="engineering-screen engineering-workspace">
      <header className="engineering-workspace__header">
        <div>
          <p className="engineering-workspace__brand">Tonnage Flow Pulse — Engineering</p>
          <p className="engineering-workspace__engineer">Signed in as {engineerName}</p>
        </div>
        <div className="engineering-workspace__header-actions">
          <span className="engineering-workspace__refreshed">
            {lastRefreshedAt
              ? `Last refreshed ${lastRefreshedAt.toLocaleTimeString()}`
              : 'Not refreshed yet'}
            {isRefreshing && ' · Refreshing…'}
          </span>
          <button type="button" className="engineering-secondary-button" onClick={refresh} disabled={isRefreshing}>
            Refresh
          </button>
          <button type="button" className="engineering-secondary-button" onClick={handleLogoutClick}>
            Log Out
          </button>
        </div>
      </header>

      {refreshError && (
        <p className="engineering-inline-error" role="alert">
          {refreshError} (showing the last data loaded successfully)
        </p>
      )}

      {handoverSuccessMessage && (
        <p className="engineering-success-note" role="status">
          {handoverSuccessMessage}
        </p>
      )}

      <div className="engineering-summary-counts">
        <span>Open: {openFaults.length}</span>
        <span>Mine: {myFaults.length}</span>
        <span>Resolved: {resolvedFaults.length}</span>
      </div>

      <nav className="engineering-tabs" aria-label="Engineering fault sections">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={
              activeTab === tab.key
                ? 'engineering-tab engineering-tab--active'
                : 'engineering-tab'
            }
            aria-pressed={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {isLoading ? (
        <p className="engineering-empty-state">Loading Engineering faults…</p>
      ) : loadError ? (
        <div className="engineering-empty-state" role="alert">
          <p>{loadError}</p>
          <button type="button" className="engineering-secondary-button" onClick={refresh}>
            Retry
          </button>
        </div>
      ) : (
        <FaultList
          faults={activeFaults}
          emptyMessage={emptyMessage}
          canAccept={(fault) => activeTab === 'open' && fault.engineer === null}
          onSelect={(fault) => setSelectedFaultId(fault.downtime_event_id)}
          onAccept={requestAccept}
        />
      )}

      {selectedFault && (
        <FaultDetailPanel
          fault={selectedFault}
          currentEngineer={engineerName}
          onClose={closeDetailPanel}
          onRequestAccept={() => requestAccept(selectedFault)}
          isAccepting={isAccepting}
          isSubmittingUpdate={isSubmittingUpdate}
          updateError={updateError}
          updateSuccessMessage={updateSuccessMessage}
          updateResetSignal={updateResetSignal}
          onSubmitUpdate={handleSubmitUpdate}
          isSubmittingClose={isSubmittingClose}
          closeError={closeError}
          onConfirmClose={handleConfirmClose}
          isSubmittingHandover={isSubmittingHandover}
          handoverError={handoverError}
          onConfirmHandover={handleConfirmHandover}
        />
      )}

      {pendingAcceptFault && (
        <ConfirmDialog
          title="Accept this job?"
          message={`This assigns ${pendingAcceptFault.machine} — ${pendingAcceptFault.reason} on ${pendingAcceptFault.production_line} to you (${engineerName}).`}
          confirmLabel="Accept Job"
          isBusy={isAccepting}
          onCancel={() => setPendingAcceptFault(null)}
          onConfirm={confirmAccept}
        />
      )}

      {acceptError && (
        <p className="engineering-inline-error" role="alert">
          {acceptError}
        </p>
      )}
    </div>
  )
}
