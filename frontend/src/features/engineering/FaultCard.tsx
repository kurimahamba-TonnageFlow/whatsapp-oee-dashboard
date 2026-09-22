import type { KeyboardEvent } from 'react'
import { engineeringStatusLabel } from './constants'
import { formatDuration, formatTimestamp } from './format'
import type { EngineeringFault } from './types'

interface FaultCardProps {
  fault: EngineeringFault
  canAccept: boolean
  onSelect: () => void
  onAccept: () => void
}

/** A single fault summary. The whole card opens the detail view; the
 * Accept button is a real, independently-focusable button inside it
 * (not a button-in-a-button) so both remain reachable by keyboard and
 * neither depends on hover. */
export function FaultCard({ fault, canAccept, onSelect, onAccept }: FaultCardProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect()
    }
  }

  return (
    <div
      className="engineering-fault-card"
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
      aria-label={`${fault.machine} - ${fault.reason}, ${fault.production_line}`}
    >
      <div className="engineering-fault-card__header">
        <span className="engineering-fault-card__line">{fault.production_line}</span>
        <span
          className={`engineering-status-pill engineering-status-pill--${fault.engineering_status
            .toLowerCase()
            .replace(/\s+/g, '-')}`}
        >
          {engineeringStatusLabel(fault.engineering_status)}
        </span>
      </div>

      <h3 className="engineering-fault-card__title">
        {fault.machine} — {fault.reason}
      </h3>

      <dl className="engineering-fault-card__details">
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
          <dt>Assigned engineer</dt>
          <dd>{fault.engineer ?? 'Unassigned'}</dd>
        </div>
        {fault.accepted_at && (
          <div>
            <dt>Accepted</dt>
            <dd>{formatTimestamp(fault.accepted_at)}</dd>
          </div>
        )}
      </dl>

      {canAccept && (
        <button
          type="button"
          className="engineering-primary-button"
          onClick={(event) => {
            event.stopPropagation()
            onAccept()
          }}
        >
          Accept Job
        </button>
      )}
    </div>
  )
}
