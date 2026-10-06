import { useState } from 'react'
import { LINE_TECHNICIANS } from '../constants'
import { ProductionRestoreForm } from '../components/ProductionRestoreForm'
import type { LineFault } from '../types'

interface FaultHandoverScreenProps {
  productionLine: string
  faults: LineFault[] | null
  loadError: string | null
  technician: string
  onTechnicianChange: (name: string) => void
  acknowledgingId: number | null
  errorMessage: string | null
  onAcknowledge: (fault: LineFault, note: string) => void
  onRetryLoad: () => void
  onContinue: () => void
  onBack: () => void
}

function openedAt(iso: string) {
  return new Date(iso).toLocaleString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/London',
  })
}

/** Faults still open on the line stay open across shifts and
 * changeovers until production is confirmed restored. The incoming technician
 * must acknowledge and escalate each before starting a run. Escalating
 * updates the existing fault - it never reports a new one. */
export function FaultHandoverScreen({
  productionLine,
  faults,
  loadError,
  technician,
  onTechnicianChange,
  acknowledgingId,
  errorMessage,
  onAcknowledge,
  onRetryLoad,
  onContinue,
  onBack,
}: FaultHandoverScreenProps) {
  const [notes, setNotes] = useState<Record<number, string>>({})
  const waiting = (faults ?? []).filter((fault) => !fault.acknowledged)

  return (
    <div className="hmi-screen hmi-fault-handover">
      <h1>Open faults on {productionLine}</h1>
      <p>
        These faults have no confirmed restart. If production has restarted, record its actual
        restart time. Otherwise acknowledge and escalate to Engineering.
      </p>

      <label className="hmi-field">
        Your name
        <select value={technician} onChange={(e) => onTechnicianChange(e.target.value)}>
          <option value="">Select technician</option>
          {LINE_TECHNICIANS.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      {loadError && (
        <div className="hmi-inline-error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="hmi-secondary-button" onClick={onRetryLoad}>
            Try again
          </button>
        </div>
      )}
      {!faults && !loadError && <p role="status">Loading open faults…</p>}

      <ul className="hmi-fault-list">
        {(faults ?? []).map((fault) => (
          <li key={fault.downtime_event_id} className="hmi-line-card">
            <h2>
              {fault.machine} — {fault.reason}
            </h2>
            <p className="hmi-line-card__detail">
              Opened {openedAt(fault.opened_at)} · reported by {fault.reported_by}
              {fault.engineer ? ` · with ${fault.engineer}` : ' · no engineer yet'}
            </p>
            <p className="hmi-line-card__detail">
              Escalated {fault.escalation_count} {fault.escalation_count === 1 ? 'time' : 'times'}
              {fault.last_escalated_by ? `, last by ${fault.last_escalated_by}` : ''}
            </p>
            {technician && <ProductionRestoreForm fault={fault} line={productionLine} technician={technician} onRestored={onRetryLoad} />}
            {fault.acknowledged ? (
              <p className="hmi-status-pill hmi-status-pill--green">✓ Acknowledged and escalated</p>
            ) : (
              <>
                <label className="hmi-field">
                  Note for Engineering (optional)
                  <input
                    type="text"
                    value={notes[fault.downtime_event_id] ?? ''}
                    onChange={(e) => setNotes((prev) => ({ ...prev, [fault.downtime_event_id]: e.target.value }))}
                  />
                </label>
                <button
                  type="button"
                  className="hmi-danger-button"
                  disabled={!technician || acknowledgingId !== null}
                  onClick={() => onAcknowledge(fault, notes[fault.downtime_event_id] ?? '')}
                >
                  {acknowledgingId === fault.downtime_event_id ? 'Escalating…' : 'Acknowledge and Escalate'}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={onContinue}
          disabled={!faults || waiting.length > 0 || !technician}
        >
          {waiting.length > 0 ? `${waiting.length} still to acknowledge` : 'Continue to Start Run'}
        </button>
      </div>
    </div>
  )
}
