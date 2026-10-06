import { clearDraft } from './drafts'
import { useRef, useSyncExternalStore } from 'react'
import { ApiRequestError, apiClient } from '../../api/client'
import { newIdempotencyKey } from '../hmi/idempotency'

export type JobAction = 'accept' | 'update' | 'close' | 'handover' | 'ready'
export type JobScope = 'fault' | 'casepacker'
interface Pending { key: string; scope: JobScope; id: number; action: JobAction; payload: unknown; created: string }
const listeners = new Set<() => void>()
const memory = new Map<string, string>()
const prefix = 'pulse.engineering.pending.v1.'
const emit = () => listeners.forEach(fn => fn())
function read(actor: string): string {
  try { return localStorage.getItem(prefix + actor) ?? '[]' } catch { return memory.get(actor) ?? '[]' }
}
function parse(raw: string): Pending[] {
  try { const value = JSON.parse(raw); return Array.isArray(value) ? value.filter(p => p && typeof p.key === 'string' && Number.isInteger(p.id) && ['fault','casepacker'].includes(p.scope) && ['accept','update','close','handover','ready'].includes(p.action)) : [] } catch { return [] }
}
function write(actor: string, items: Pending[]) {
  const raw = JSON.stringify(items)
  // Refuse to submit if durable recovery cannot be saved. Existing pending retries remain usable.
  localStorage.setItem(prefix + actor, raw)
  memory.set(actor, raw); emit()
}
function subscribe(fn: () => void) { listeners.add(fn); window.addEventListener('storage', fn); return () => { listeners.delete(fn); window.removeEventListener('storage', fn) } }
export function useEngineeringWrites(actor: string, token: string) {
  const busy = useRef(new Set<string>()).current
  const raw = useSyncExternalStore(subscribe, () => read(actor))
  const pending = parse(raw)
  async function perform<T>(scope: JobScope, id: number, action: JobAction, payload: unknown, send: (key: string) => Promise<T>, retry?: Pending): Promise<T> {
    const lock = `${actor}:${scope}:${id}`
    if (busy.has(lock)) throw new Error('This job already has a save in progress.')
    const existing = parse(read(actor)).find(p => p.scope === scope && p.id === id)
    if (existing && !retry) throw new Error('Resolve the pending action above before submitting another change to this job.')
    const entry = retry ?? { scope, id, action, payload, key: newIdempotencyKey(), created: new Date().toISOString() }
    if (!retry) {
      try { write(actor, [...parse(read(actor)), entry]) }
      catch { throw new Error('Browser storage is unavailable. Enable storage before saving so this action can be recovered safely.') }
    }
    busy.add(lock)
    try {
      const result = await send(entry.key)
      write(actor, parse(read(actor)).filter(p => p.key !== entry.key))
      clearDraft(scope === 'casepacker' ? `casepacker:${actor}:${id}` : `fault:${actor}:${id}:${action}`)
      return result
    } catch (error) {
      if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500 && ![401,403,408,429].includes(error.status)) {
        write(actor, parse(read(actor)).filter(p => p.key !== entry.key))
      }
      throw error
    } finally { busy.delete(lock); emit() }
  }
  function retry(entry: Pending) {
    // Server replay retention is 90 days. Do not risk treating an ancient action as new.
    if (!Number.isFinite(Date.parse(entry.created)) || Date.now() - Date.parse(entry.created) > 89 * 86400000) {
      return Promise.reject(new Error('This pending action is too old to retry safely. Ask a manager to check its saved history.'))
    }
    const path = entry.scope === 'casepacker'
      ? `/api/v1/engineering/casepacker-requests/${entry.id}/actions`
      : `/api/v1/engineering/faults/${entry.id}/${entry.action === 'update' ? 'updates' : entry.action}`
    return perform(entry.scope, entry.id, entry.action, entry.payload,
      key => apiClient.post(path, entry.payload, { token, idempotencyKey: key }), entry)
  }
  return { pending, perform, retry }
}
