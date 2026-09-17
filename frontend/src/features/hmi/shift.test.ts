import { describe, expect, it } from 'vitest'
import { resolveCurrentShift } from './shift'

describe('resolveCurrentShift', () => {
  it('resolves Days for 06:00-13:59', () => {
    expect(resolveCurrentShift(new Date(2026, 0, 1, 6, 0)).name).toBe('Days')
    expect(resolveCurrentShift(new Date(2026, 0, 1, 13, 59)).name).toBe('Days')
  })

  it('resolves Afternoons for 14:00-21:59', () => {
    expect(resolveCurrentShift(new Date(2026, 0, 1, 14, 0)).name).toBe('Afternoons')
    expect(resolveCurrentShift(new Date(2026, 0, 1, 21, 59)).name).toBe('Afternoons')
  })

  it('resolves Nights for 22:00-23:59 and 00:00-05:59 (wraps midnight)', () => {
    expect(resolveCurrentShift(new Date(2026, 0, 1, 22, 0)).name).toBe('Nights')
    expect(resolveCurrentShift(new Date(2026, 0, 1, 23, 59)).name).toBe('Nights')
    expect(resolveCurrentShift(new Date(2026, 0, 1, 0, 0)).name).toBe('Nights')
    expect(resolveCurrentShift(new Date(2026, 0, 1, 5, 59)).name).toBe('Nights')
  })
})
