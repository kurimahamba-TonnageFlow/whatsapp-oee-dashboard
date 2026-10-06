import { faultSection, isSbsMachine, sbsEquipmentLabel } from '../faultSections'
import { useState } from 'react'
import type { HmiConfigMachine } from '../../../types/api'
import type { FaultReportPayload, FaultReportResponse } from '../types'

interface ReportToEngineerScreenProps {
  productionLine: string
  machines: HmiConfigMachine[]
  isSubmitting: boolean
  result: FaultReportResponse | null
  errorMessage: string | null
  onSubmit: (input: {
    machine: string
    machineId: number | null
    buttonId: number | null
    reason: string
    note: string
    startedAt?: string
    restoredAt?: string
  }) => void
  pendingReport?: FaultReportPayload | null
  onRetry?: () => void
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
  pendingReport = null,
  onRetry,
  onCancel,
  onDone,
}: ReportToEngineerScreenProps) {
  const [machine, setMachine] = useState('')
  const [sbsOpen, setSbsOpen] = useState(false)
  const [section, setSection] = useState('')
  const [otherMachine, setOtherMachine] = useState('')
  const [buttonId, setButtonId] = useState('')
  const [faultReason, setFaultReason] = useState('')
  const [note, setNote] = useState('')
  const [selfResolved, setSelfResolved] = useState(false)
  const [startedAt, setStartedAt] = useState('')
  const [restoredAt, setRestoredAt] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  if (result) {
    return (
      <div className="hmi-screen hmi-report-engineer" role="status">
        <p className="hmi-run-started__mark">{result.production_status === 'Resolved' ? '✓ Resolved downtime recorded' : '✓ Reported to Engineering'}</p>
        <p>
          {result.production_status === 'Resolved'
            ? `Fault ${result.fault_id} on ${result.machine} was resolved by the line technician. No Engineering call was created.`
            : `Fault ${result.fault_id} on ${result.machine} is now with Engineering (${result.engineering_status}).`}
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-primary-button" onClick={onDone}>
            Back to Active Run
          </button>
        </div>
      </div>
    )
  }

  if (pendingReport) {
    return <div className="hmi-screen hmi-report-engineer">
      <h1>Confirm previous fault report</h1>
      <p>Pulse has not confirmed this report. Retry the original details to avoid a duplicate.</p>
      <p><strong>Machine:</strong> {pendingReport.machine}</p>
      <p><strong>Reason:</strong> {pendingReport.reason}</p>
      <p><strong>Reported by:</strong> {pendingReport.reported_by}</p>
      {pendingReport.note && <p><strong>Details:</strong> {pendingReport.note}</p>}
      {pendingReport.outcome === 'resolved' && <>
        <p>Technician resolved the stop. No Engineering call requested.</p>
        <p>Stop started: {pendingReport.started_at ? new Date(pendingReport.started_at).toLocaleString('en-GB') : 'Not recorded'}</p>
        <p>Production restarted: {pendingReport.restored_at ? new Date(pendingReport.restored_at).toLocaleString('en-GB') : 'Not recorded'}</p>
      </>}
      {errorMessage && <p className="hmi-inline-error" role="alert">{errorMessage}</p>}
      <div className="hmi-form-actions">
        <button type="button" className="hmi-primary-button" disabled={isSubmitting} onClick={onRetry}>{isSubmitting ? 'Checking...' : 'Retry original report'}</button>
        <button type="button" className="hmi-secondary-button" disabled={isSubmitting} onClick={onCancel}>Back to Active Run</button>
      </div>
    </div>
  }

  const selectedMachine = machines.find((m) => m.name === machine)
  const faultButtons =
    selectedMachine?.buttons.filter((b) => b.event_type === 'unplanned_fault') ?? []
  const selectedButton = faultButtons.find((b) => String(b.id) === buttonId)
  const noteRequired = selfResolved || !selectedButton
  const sbsMachines = machines.filter(m => isSbsMachine(m.name))
  const usesSections = !!selectedMachine && isSbsMachine(selectedMachine.name)
  const sections = [...new Set(faultButtons.map(b => faultSection(b.name)))]
  const visibleFaults = usesSections ? faultButtons.filter(b => faultSection(b.name) === section) : faultButtons
  function chooseMachine(name: string) {
    setMachine(name); setButtonId(''); setFaultReason(''); setSection(''); setValidationError(null)
  }

  function handleSubmit() {
    const machineName = machine === '__other__' ? otherMachine.trim() : machine.trim()
    const reason = selectedButton ? selectedButton.name : [usesSections ? section : '', faultReason.trim()].filter(Boolean).join(': ')

    if (!machineName || (!selectedButton && !faultReason.trim()) || (usesSections && !section)) {
      setValidationError('Select a machine and a fault reason.')
      return
    }

    if (noteRequired && !note.trim()) {
      setValidationError(selfResolved ? 'Add a note explaining what you did to resolve the fault.' : 'Add a note describing the fault when no fault button is selected.')
      return
    }
    if (selfResolved && (!startedAt || !restoredAt || !Number.isFinite(new Date(startedAt).getTime()) || !Number.isFinite(new Date(restoredAt).getTime()) || new Date(restoredAt) < new Date(startedAt))) {
      setValidationError('Enter the actual stop and restart times. Restart cannot be before the stop.')
      return
    }

    setValidationError(null)
    onSubmit({
      machine: machineName,
      machineId: selectedMachine ? selectedMachine.id : null,
      buttonId: selectedButton ? selectedButton.id : null,
      reason,
      note: [usesSections ? `Section: ${section}` : '', note.trim()].filter(Boolean).join('\n'),
      ...(selfResolved ? { startedAt: new Date(startedAt).toISOString(), restoredAt: new Date(restoredAt).toISOString() } : {}),
    })
  }

  return (
    <div className="hmi-screen hmi-report-engineer">
      <h1>Report to Engineer — {productionLine}</h1>
      <p>Fixed it yourself? Choose Resolved and record what you did. Otherwise call Engineering.</p>
      <div className="hmi-form-actions">
        <button type="button" className="hmi-secondary-button" aria-pressed={selfResolved} disabled={isSubmitting} onClick={() => setSelfResolved(true)}>Resolved</button>
        <button type="button" className="hmi-secondary-button" aria-pressed={!selfResolved} disabled={isSubmitting} onClick={() => setSelfResolved(false)}>Call Engineer</button>
      </div>
      {selfResolved && <>
        <label className="hmi-field">Stop started (tablet local time)<input type="datetime-local" value={startedAt} onChange={(e) => setStartedAt(e.target.value)} /></label>
        <label className="hmi-field">Production restarted (tablet local time)<input type="datetime-local" value={restoredAt} onChange={(e) => setRestoredAt(e.target.value)} /></label>
      </>}

      {machines.length > 0 ? <>
        <fieldset className="hmi-fault-choices" disabled={isSubmitting}>
          <legend>Machine or section</legend>
          <div className="hmi-button-grid">
            {sbsMachines.length > 0 && <button type="button" className="hmi-secondary-button" aria-pressed={sbsOpen} onClick={() => { setSbsOpen(true); chooseMachine('') }}>SBS</button>}
            {machines.filter(m => !isSbsMachine(m.name)).map(m => <button key={m.id} type="button" className="hmi-secondary-button" aria-pressed={machine === m.name} onClick={() => { setSbsOpen(false); chooseMachine(m.name) }}>{m.name}</button>)}
            <button type="button" className="hmi-secondary-button" aria-pressed={machine === '__other__'} onClick={() => { setSbsOpen(false); chooseMachine('__other__') }}>Other machine / section</button>
          </div>
        </fieldset>
        {sbsOpen && <fieldset className="hmi-fault-choices" disabled={isSubmitting}>
          <legend>SBS equipment</legend>
          <div className="hmi-button-grid">{sbsMachines.map(m => <button key={m.id} type="button" className="hmi-secondary-button" aria-pressed={machine === m.name} onClick={() => chooseMachine(m.name)}>{sbsEquipmentLabel(m.name)}</button>)}</div>
        </fieldset>}
      </> : <label className="hmi-field">Machine or section<input maxLength={120} value={machine} onChange={e => chooseMachine(e.target.value)} /></label>}
      {machine === '__other__' && <label className="hmi-field">Name the machine or section<input value={otherMachine} onChange={e => setOtherMachine(e.target.value)} maxLength={120} /></label>}
      {usesSections && <fieldset className="hmi-fault-choices" disabled={isSubmitting}>
        <legend>Section</legend>
        <div className="hmi-button-grid">
          {sections.map(name => <button key={name} type="button" className="hmi-secondary-button" aria-pressed={section === name} onClick={() => { setSection(name); setButtonId(''); setFaultReason('') }}>{name}</button>)}
          <button type="button" className="hmi-secondary-button" aria-pressed={section === 'Other section'} onClick={() => { setSection('Other section'); setButtonId('__other__'); setFaultReason('') }}>Other section</button>
        </div>
      </fieldset>}
      {machine && (!usesSections || section) && <>
        {visibleFaults.length > 0 ? <fieldset className="hmi-fault-choices" disabled={isSubmitting}>
          <legend>Fault reason</legend>
          <div className="hmi-button-grid">
            {visibleFaults.map(button => <button type="button" key={button.id} className="hmi-secondary-button" aria-pressed={buttonId === String(button.id)} onClick={() => setButtonId(String(button.id))}>{button.name}</button>)}
            <button type="button" className="hmi-secondary-button" aria-pressed={buttonId === '__other__'} onClick={() => setButtonId('__other__')}>Other fault reason</button>
          </div>
        </fieldset> : <label className="hmi-field">Fault reason<input maxLength={usesSections ? 118 - section.length : 120} value={faultReason} onChange={e => setFaultReason(e.target.value)} /></label>}
        {visibleFaults.length > 0 && buttonId === '__other__' && <label className="hmi-field">Describe the fault<input value={faultReason} onChange={e => setFaultReason(e.target.value)} maxLength={120} /></label>}
      </>}

      <label className="hmi-field">
        {noteRequired ? 'Note (required)' : 'Note (optional)'}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={usesSections ? 489 - section.length : 500} />
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
          {isSubmitting ? 'Reporting…' : selfResolved ? 'Save resolved downtime' : 'Report to Engineer'}
        </button>
      </div>
    </div>
  )
}
