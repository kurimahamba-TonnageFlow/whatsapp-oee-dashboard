import { useRef, useState } from 'react'
import { ApiRequestError } from '../../api/client'
import { useManagementSession } from '../management/session/useManagementSession'
import { useProtectedData } from '../management/session/useProtectedData'
import { newIdempotencyKey } from '../hmi/idempotency'
import type { HmiLineState } from '../hmi/types'
import * as dashboardApi from './api'
import { formatDateTime } from './format'
import { Panel } from './ui/Panel'

const CHOICES: Array<{ kind: dashboardApi.NextStepKind; label: string; help: string }> = [
  { kind: 'handover', label: 'End Shift (handover)', help: 'Planned, until the next run starts.' },
  { kind: 'changeover', label: 'Changeover', help: 'Planned; End Changeover is then pressed on the HMI.' },
  { kind: 'not_scheduled', label: 'Not scheduled', help: 'The line was not scheduled to produce: no target, not downtime.' },
  { kind: 'other', label: 'Other', help: 'Unplanned, with a written reason.' },
]

/** Lines where End Run was confirmed but nobody chose what happened next.
 * They stay here - on any day - until a technician (HMI) or a manager
 * (this panel) records it; the line cannot start a run until then. */
export function NextStepDecisions() {
  const lines = useProtectedData((token, signal) => dashboardApi.getLineDecisions(token, signal), 'line-decisions')
  const waiting = (lines.data?.lines ?? []).filter((line) => !line.has_active_run && line.awaiting_next_step)

  if (waiting.length === 0) return null

  return (
    <Panel title="Run ended — next step not chosen">
      <p className="pd-footnote">
        A new run cannot start on these lines until this is recorded. The event you choose starts when the run
        ended, so the whole gap is accounted for.
      </p>
      {waiting.map((line) => (
        <DecisionRow key={line.production_line} line={line} onResolved={lines.reload} />
      ))}
    </Panel>
  )
}

function DecisionRow({ line, onResolved }: { line: HmiLineState; onResolved: () => void }) {
  const { session, handleAuthError } = useManagementSession()
  const ended = line.awaiting_next_step!
  const [kind, setKind] = useState<dashboardApi.NextStepKind | ''>('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // One key per logical choice, reused on every retry until it succeeds.
  const keyRef = useRef<{ fingerprint: string; key: string } | null>(null)

  function submit() {
    if (!session || saving || !kind) return
    if (kind === 'other' && !reason.trim()) {
      setError('Write the reason the line was stopped.')
      return
    }
    const payload = { kind, reason: kind === 'other' ? reason.trim() : null }
    const fingerprint = JSON.stringify(payload)
    if (keyRef.current?.fingerprint !== fingerprint) keyRef.current = { fingerprint, key: newIdempotencyKey() }

    setSaving(true)
    setError(null)
    dashboardApi
      .resolveNextStep(session.token, line.production_line, payload, keyRef.current.key)
      .then(() => {
        keyRef.current = null
        onResolved()
      })
      .catch((failure: unknown) => {
        if (handleAuthError(failure)) return
        setError(
          failure instanceof ApiRequestError && failure.status < 500 && failure.status !== 0
            ? failure.message
            : 'Could not save this to Pulse. Nothing was recorded - please try again.',
        )
      })
      .finally(() => setSaving(false))
  }

  return (
    <div className="pd-decision" aria-label={`${line.production_line} next step`}>
      <p className="pd-decision__what">
        <strong>{line.production_line}</strong> · {ended.line_technician ?? 'A technician'}'s run ended{' '}
        {formatDateTime(ended.finished_at)}
      </p>
      <fieldset className="pd-decision__choices">
        <legend className="pd-visually-hidden">What happened after the run on {line.production_line}?</legend>
        {CHOICES.map((choice) => (
          <label key={choice.kind} className="pd-decision__choice" title={choice.help}>
            <input
              type="radio"
              name={`next-step-${line.production_line}`}
              value={choice.kind}
              checked={kind === choice.kind}
              onChange={() => setKind(choice.kind)}
            />
            {choice.label}
          </label>
        ))}
      </fieldset>
      {kind === 'other' && (
        <label className="pd-inline-field pd-decision__reason">
          <span>Reason</span>
          <input type="text" value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      )}
      <button type="button" className="pd-button" onClick={submit} disabled={!kind || saving}>
        {saving ? 'Saving…' : 'Record as manager'}
      </button>
      {error && (
        <p className="pd-error-text" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
