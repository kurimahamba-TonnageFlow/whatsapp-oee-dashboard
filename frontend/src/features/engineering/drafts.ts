import { useCallback, useState } from 'react'
const prefix = 'pulse.engineering.draft.v1.'
export function clearDraft(key: string) { try { localStorage.removeItem(prefix + key) } catch { /* Existing pending action is stored separately. */ } }
export function useDraft<T>(key: string | undefined, initial: T): [T, (value: T | ((current: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    if (!key) return initial
    try {
      const saved = JSON.parse(localStorage.getItem(prefix + key) ?? 'null')
      if (typeof initial === 'string') return typeof saved === 'string' ? saved as T : initial
      return saved && typeof saved === 'object' && !Array.isArray(saved) ? { ...initial, ...saved } : initial
    } catch { return initial }
  })
  const update = useCallback((next: T | ((current: T) => T)) => setValue(current => {
    const resolved = typeof next === 'function' ? (next as (v: T) => T)(current) : next
    if (key) { try { localStorage.setItem(prefix + key, JSON.stringify(resolved)) } catch { /* Do not discard the in-memory draft. */ } }
    return resolved
  }), [key])
  return [value, update]
}
