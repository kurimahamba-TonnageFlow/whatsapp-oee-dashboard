import { useEngineeringWrites } from './recovery'
import { RecoveryPanel } from './RecoveryPanel'
import { useDraft } from './drafts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../../api/client'
import { actOnCasepacker, getCasepackerRequests, type CasepackerRequest } from './casepackerApi'

interface Props { token: string; engineerName: string; onSessionExpired: () => void }
export function CasepackerQueue({ token, engineerName, onSessionExpired }: Props) {
  const [items, setItems] = useState<CasepackerRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [recoveryVersion, setRecoveryVersion] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const latest = useRef<AbortController | null>(null)
  const refresh = useCallback(async (signal?: AbortSignal) => {
    latest.current?.abort()
    const controller = new AbortController()
    latest.current = controller
    if (signal?.aborted) controller.abort()
    const cancel = () => controller.abort()
    signal?.addEventListener('abort', cancel, { once: true })
    try {
      const response = await getCasepackerRequests(token, controller.signal)
      if (!controller.signal.aborted) { setItems(response.items); setLoaded(true); setError(null) }
    } catch (err) {
      if (controller.signal.aborted) return
      if (err instanceof ApiRequestError && err.status === 401) onSessionExpired()
      else setError('Could not refresh casepacker requests. Check again before relying on this list.')
    } finally { signal?.removeEventListener('abort', cancel) }
  }, [token, onSessionExpired])
  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    const timer = window.setInterval(() => { void refresh(controller.signal) }, 10000)
    return () => { controller.abort(); latest.current?.abort(); window.clearInterval(timer) }
  }, [refresh])
  return <section aria-label="Casepacker changeovers" className="engineering-casepacker-queue">
    <h2>Casepacker changeovers</h2>
    <RecoveryPanel actor={engineerName} token={token} scope="casepacker" onSaved={() => { setRecoveryVersion(n => n + 1); return refresh() }} onSessionExpired={onSessionExpired} />
    <p>Accept the request, record the work and mark the casepacker ready. Production stays blocked until ready.</p>
    <button className="engineering-secondary-button" onClick={() => { void refresh() }}>Refresh changeovers</button>
    {error && <p role="alert">{error}</p>}
    {!loaded && !error && <p>Loading changeover requests...</p>}
    {loaded && !error && items.length === 0 && <p>No casepacker requests waiting for the next run.</p>}
    {items.map(item => <CasepackerJob key={`${item.id}:${recoveryVersion}`} item={item} token={token} engineerName={engineerName} onSessionExpired={onSessionExpired} onSaved={() => refresh()} />)}
  </section>
}

function CasepackerJob({ item, token, engineerName, onSessionExpired, onSaved }: Props & { item: CasepackerRequest; onSaved: () => Promise<void> }) {
  const [note, setNote] = useDraft(`casepacker:${engineerName}:${item.id}`, '')
  const writes = useEngineeringWrites(engineerName, token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmReady, setConfirmReady] = useState(false)
  const [confirmHandover, setConfirmHandover] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)
  const own = item.engineer === engineerName
  async function act(action: 'accept' | 'update' | 'ready' | 'handover') {
    if (busy) return
    const bodyNote = action === 'accept' ? '' : note.trim()
    if (action !== 'accept' && !bodyNote) { setError('Add details of the work first.'); return }
    setBusy(true); setError(null); setSuccess(null)
    try {
      await writes.perform('casepacker', item.id, action, { action, note: bodyNote }, key => actOnCasepacker(token, item.id, action, bodyNote, key))
      setNote(''); setConfirmReady(false); setConfirmHandover(false)
      setSuccess(action === 'ready' ? 'Casepacker ready. The technician can continue.' : 'Saved.')
      await onSaved()
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) onSessionExpired()
      setError(err instanceof Error ? err.message : 'Could not confirm the save. Use Retry original action above.')
    } finally { setBusy(false) }
  }
  return <article className="engineering-casepacker-job">
    <h3>{item.production_line} - Casepacker</h3>
    <p><strong>{item.ready_at ? 'Ready' : item.engineer ? `Accepted by ${item.engineer}` : 'Waiting for Engineering'}</strong></p>
    <p>{item.details}</p>
    <p>Requested by {item.requested_by} | {new Date(item.requested_at).toLocaleString('en-GB')}</p>
    {item.updates.map(update => <p key={update.id}>{update.engineer} | {update.action} | {new Date(update.created_at).toLocaleString('en-GB')}{update.note && `: ${update.note}`}</p>)}
    {!item.ready_at && !item.engineer && <button className="engineering-primary-button" disabled={busy} onClick={() => { void act('accept') }}>Accept changeover</button>}
    {!item.ready_at && own && <>
      <label className="engineering-casepacker-note">Casepacker work details
        <textarea value={note} maxLength={2000} disabled={busy} onChange={e => setNote(e.target.value)} />
      </label>
      <button className="engineering-secondary-button" disabled={busy || !note.trim()} onClick={() => { void act('update') }}>Add changeover update</button>
      <button className="engineering-primary-button" disabled={busy || !note.trim()} onClick={() => { setConfirmHandover(false); setConfirmReady(true) }}>Casepacker ready</button>
      <button className="engineering-secondary-button" disabled={busy || !note.trim()} onClick={() => { setConfirmReady(false); setConfirmHandover(true) }}>Hand over changeover</button>
      {confirmHandover && <div role="group" aria-label="Confirm changeover handover">
        <p>Save these details and release the job for another engineer. Production stays blocked until the casepacker is ready.</p>
        <button className="engineering-primary-button" disabled={busy} onClick={() => { void act('handover') }}>Confirm changeover handover</button>
        <button className="engineering-secondary-button" disabled={busy} onClick={() => setConfirmHandover(false)}>Keep this job</button>
      </div>}
      {confirmReady && <div role="group" aria-label="Confirm casepacker ready">
        <p>Confirm the requested format and program are set and the casepacker is ready for the next run.</p>
        <button className="engineering-primary-button" disabled={busy} onClick={() => { void act('ready') }}>Confirm casepacker ready</button>
        <button className="engineering-secondary-button" disabled={busy} onClick={() => setConfirmReady(false)}>Keep working</button>
      </div>}
    </>}
    {success && <p role="status">{success}</p>}
    {error && <p role="alert">{error}</p>}
  </article>
}
