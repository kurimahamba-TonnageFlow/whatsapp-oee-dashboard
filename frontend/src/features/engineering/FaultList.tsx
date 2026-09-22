import { FaultCard } from './FaultCard'
import type { EngineeringFault } from './types'

interface FaultListProps {
  faults: EngineeringFault[]
  emptyMessage: string
  canAccept: (fault: EngineeringFault) => boolean
  onSelect: (fault: EngineeringFault) => void
  onAccept: (fault: EngineeringFault) => void
}

export function FaultList({ faults, emptyMessage, canAccept, onSelect, onAccept }: FaultListProps) {
  if (faults.length === 0) {
    return <p className="engineering-empty-state">{emptyMessage}</p>
  }

  return (
    <div className="engineering-fault-list">
      {faults.map((fault) => (
        <FaultCard
          key={fault.downtime_event_id}
          fault={fault}
          canAccept={canAccept(fault)}
          onSelect={() => onSelect(fault)}
          onAccept={() => onAccept(fault)}
        />
      ))}
    </div>
  )
}
