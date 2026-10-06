import { useState } from 'react'
import { ApiRequestError } from '../../api/client'
import { useEngineeringWrites, type JobScope } from './recovery'

export function RecoveryPanel({ actor, token, scope, onSaved, onSessionExpired }: { actor: string; token: string; scope: JobScope; onSaved: () => unknown; onSessionExpired: () => void }) {
  const writes = useEngineeringWrites(actor, token)
  const [feedback, setFeedback] = useState('')
  const [retrying, setRetrying] = useState(false)
  return <section aria-label={`${scope} pending actions`}>
    {writes.pending.filter(p => p.scope === scope).map(p => <article key={p.key} className="engineering-inline-note">
      <strong>Unconfirmed {p.action}: {scope === 'fault' ? 'fault' : 'changeover'} #{p.id}</strong>
      <p>The action may already have saved. Retry the original action to confirm it safely.</p>
      <dl>{Object.entries((p.payload ?? {}) as Record<string, unknown>).filter(([, value]) => value != null && value !== '').map(([name, value]) => <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{String(value)}</dd></div>)}</dl>
      <button className="engineering-secondary-button" disabled={retrying} onClick={async () => {
        setRetrying(true); setFeedback('')
        try { await writes.retry(p); setFeedback('Original action confirmed.'); await onSaved() }
        catch (err) { if (err instanceof ApiRequestError && err.status === 401) onSessionExpired(); setFeedback(err instanceof Error ? err.message : 'Could not confirm the action.') }
        finally { setRetrying(false) }
      }}>Retry original {p.action}</button>
    </article>)}
    {feedback && <p role="status">{feedback}</p>}
  </section>
}
