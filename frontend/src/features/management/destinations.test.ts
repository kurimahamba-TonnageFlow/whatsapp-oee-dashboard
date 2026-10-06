import { describe, expect, it } from 'vitest'
import { formatSessionEnd, protectedDestinationFrom } from './destinations'

describe('protectedDestinationFrom', () => {
  it.each([
    ['/dashboard', 'Production dashboard'],
    ['/management/performance', 'Technician performance'],
  ])('accepts the known protected page %s', (from, label) => {
    expect(protectedDestinationFrom({ from })).toEqual({ path: from, label })
  })

  it.each([
    null,
    undefined,
    'dashboard',
    {},
    { from: 42 },
    { from: '/hmi' },
    { from: '/management' },
    { from: 'https://example.invalid/dashboard' },
    { from: '/dashboard/../hmi' },
    { from: 'constructor' },
    { from: 'toString' },
  ])('ignores anything that is not a known protected page: %j', (state) => {
    expect(protectedDestinationFrom(state)).toBeNull()
  })
})

describe('formatSessionEnd', () => {
  it('shows the UK wall-clock time (BST in summer)', () => {
    expect(formatSessionEnd('2026-09-25T09:30:00+00:00')).toBe('10:30')
  })

  it('shows the UK wall-clock time (GMT in winter)', () => {
    expect(formatSessionEnd('2026-12-01T09:30:00+00:00')).toBe('09:30')
  })

  it('returns null for an unparseable timestamp', () => {
    expect(formatSessionEnd('not-a-date')).toBeNull()
  })
})
