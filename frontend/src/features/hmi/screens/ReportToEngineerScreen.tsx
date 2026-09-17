import { useState } from 'react'
import type { HmiConfigMachine } from '../../../types/api'
import type { EngineerReportResult } from '../awaitingApiIntegration'

interface ReportToEngineerScreenProps {
  productionLine: string
  machines: HmiConfigMachine[]
  isSubmitting: boolean
  result: EngineerReportResult | null
  errorMessage: string | null
  onSubmit: (input: { machine: string; faultReason: string; note: string }) => void
  onCancel: () => void
  onDone: () => void
}

export function ReportToEngineerScreen({
  productionLine,
  machines,
  isSubmitting,
  result,
  errorMessage,
  onSubmit,
  onCancel,
  onDone,
}: ReportToEngineerScreenProps) {
  const [machine, setMachine] = useState('')
  const [faultReason, setFaultReason] = useState('')
  const [note, setNote] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  if (result) {
    return (
      <div className="hmi-screen hmi-report-engineer" role="status">
        <p className="hmi-run-started__mark">✓ Reported to Engineering</p>
        <p>Reference: {result.reference}</p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-primary-button" onClick={onDone}>
            Back to Active Run
          </button>
        </div>
      </div>
    )
  }

  const selectedMachine = machines.find((m) => m.name === machine)
  const faultButtons = selectedMachine?.buttons.filter((b) => b.event_type === 'unplanned_fault') ?? []

  function handleSubmit() {
    if (!machine.trim() || !faultReason.trim()) {
      setValidationError('Select a machine and a fault reason.')
      return
    }
    setValidationError(null)
    onSubmit({ machine, faultReason, note })
  }

  return (
    <div className="hmi-screen hmi-report-engineer">
      <h1>Report to Engineer — {productionLine}</h1>

      <label className="hmi-field">
        Machine or section
        {machines.length > 0 ? (
          <select value={machine} onChange={(e) => { setMachine(e.target.value); setFaultReason('') }}>
            <option value="">Select…</option>
            {machines.map((m) => (
              <option key={m.id} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={machine}
            onChange={(e) => setMachine(e.target.value)}
            placeholder="e.g. BV1"
          />
        )}
      </label>

      <label className="hmi-field">
        Fault reason
        {faultButtons.length > 0 ? (
          <select value={faultReason} onChange={(e) => setFaultReason(e.target.value)}>
            <option value="">Select…</option>
            {faultButtons.map((button) => (
              <option key={button.id} value={button.name}>
                {button.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={faultReason}
            onChange={(e) => setFaultReason(e.target.value)}
            placeholder="e.g. Casepacker Jam"
          />
        )}
      </label>

      <label className="hmi-field">
        Note (optional)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
      </label>

      {validationError && (
        <span className="hmi-field-error" role="alert">
          {validationError}
        </span>
      )}

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button
          type="button"
          className="hmi-secondary-button"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Back
        </button>
        <button
          type="button"
          className="hmi-danger-button"
          onClick={handleSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Reporting…' : 'Report to Engineer'}
        </button>
      </div>
    </div>
  )
}
