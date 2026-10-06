import { useState } from 'react'

interface EndRunNextScreenProps {
  productionLine: string
  technician: string
  /** Choosing later (from Home): the event covers the time since then. */
  endedAt?: string | null
  isSubmitting: boolean
  errorMessage: string | null
  onEndShift: () => void
  onChangeover: (casepackerRequired: boolean, details: string) => void
  onOther: (reason: string) => void
  onNotScheduled: () => void
}

/** After End Run: the run's output clock has stopped. What happens next
 * on the line decides what is recorded against it. */
export function EndRunNextScreen({
  productionLine,
  technician,
  endedAt = null,
  isSubmitting,
  errorMessage,
  onEndShift,
  onChangeover,
  onOther,
  onNotScheduled,
}: EndRunNextScreenProps) {
  const [changeoverOpen, setChangeoverOpen] = useState(false)
  const [casepackerRequired, setCasepackerRequired] = useState<boolean | null>(null)
  const [casepackerDetails, setCasepackerDetails] = useState('')
  const [otherOpen, setOtherOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)

  return (
    <div className="hmi-screen hmi-end-run-next">
      <p className="hmi-run-started__mark">✓ Run ended</p>
      <h1>What happens next on {productionLine}?</h1>
      <p>{technician}'s run is closed and its output clock has stopped.</p>
      {endedAt && (
        <p className="hmi-timer-notice" role="status">
          This run ended {formatEndedAt(endedAt)}. Your choice covers all the time since then.
        </p>
      )}

      {changeoverOpen ? (
        <div>
          <h2>Does the casepacker need a format or program change?</h2>
          <p>For example: 1 kg x 10 to 1 kg x 8, a different 500 g box, or a customer program.</p>
          <div className="hmi-form-actions">
            <button type="button" className="hmi-secondary-button" aria-pressed={casepackerRequired === true} disabled={isSubmitting} onClick={() => setCasepackerRequired(true)}>Yes - call Engineering</button>
            <button type="button" className="hmi-secondary-button" aria-pressed={casepackerRequired === false} disabled={isSubmitting} onClick={() => setCasepackerRequired(false)}>No casepacker change</button>
          </div>
          {casepackerRequired && <label className="hmi-field">
            Required casepacker format or program
            <textarea value={casepackerDetails} maxLength={500} disabled={isSubmitting} onChange={e => setCasepackerDetails(e.target.value)} />
            <span className="hmi-field-help">Include the next customer, pack size and box format. Engineering must mark it ready before the next run can start.</span>
          </label>}
          <div className="hmi-form-actions">
            <button type="button" className="hmi-secondary-button" disabled={isSubmitting} onClick={() => setChangeoverOpen(false)}>Back</button>
            <button type="button" className="hmi-primary-button" disabled={isSubmitting || casepackerRequired === null || (casepackerRequired && !casepackerDetails.trim())}
              onClick={() => onChangeover(casepackerRequired === true, casepackerRequired ? casepackerDetails.trim() : '')}>
              {isSubmitting ? 'Starting...' : 'Start Changeover'}
            </button>
          </div>
        </div>
      ) : !otherOpen ? (
        <div className="hmi-button-grid">
          <button type="button" className="hmi-primary-button" onClick={onEndShift} disabled={isSubmitting}>
            End Shift
            <small>Starts the handover timer until the next technician starts a run.</small>
          </button>
          <button type="button" className="hmi-secondary-button" onClick={() => setChangeoverOpen(true)} disabled={isSubmitting}>
            Changeover
            <small>Starts the changeover timer.</small>
          </button>
          <button type="button" className="hmi-secondary-button" onClick={onNotScheduled} disabled={isSubmitting}>
            Not scheduled
            <small>The line is not scheduled to produce. Not downtime.</small>
          </button>
          <button type="button" className="hmi-secondary-button" onClick={() => setOtherOpen(true)} disabled={isSubmitting}>
            Other
            <small>The line is stopped for another reason.</small>
          </button>
        </div>
      ) : (
        <>
          <label className="hmi-field">
            Why is the line stopped?
            <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
            {reasonError && (
              <span className="hmi-field-error" role="alert">
                {reasonError}
              </span>
            )}
            <span className="hmi-field-help">This time counts as unplanned downtime on the line.</span>
          </label>
          <div className="hmi-form-actions">
            <button type="button" className="hmi-secondary-button" onClick={() => setOtherOpen(false)} disabled={isSubmitting}>
              Back
            </button>
            <button
              type="button"
              className="hmi-primary-button"
              disabled={isSubmitting}
              onClick={() => {
                if (!reason.trim()) {
                  setReasonError('Write the reason before starting the timer.')
                  return
                }
                setReasonError(null)
                onOther(reason.trim())
              }}
            >
              {isSubmitting ? 'Starting…' : 'Start Stop Timer'}
            </button>
          </div>
        </>
      )}

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  )
}

function formatEndedAt(iso: string): string {
  const at = new Date(iso)
  const time = at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (at.toDateString() === new Date().toDateString()) return `at ${time} today`
  return `at ${time} on ${at.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}`
}
