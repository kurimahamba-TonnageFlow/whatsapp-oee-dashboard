import { describe, expect, it } from 'vitest'
import {
  barWidthPercent,
  formatCalendarDate,
  formatDateTime,
  formatMinutes,
  formatPallets,
  formatPercent,
  formatTonnes,
  localDatePart,
  MISSING,
} from './format'

describe('missing values are never shown as zero', () => {
  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY])('%s → "—"', (value) => {
    expect(formatTonnes(value)).toBe(MISSING)
    expect(formatPallets(value)).toBe(MISSING)
    expect(formatPercent(value)).toBe(MISSING)
    expect(formatMinutes(value)).toBe(MISSING)
  })

  it('shows a real zero as zero', () => {
    expect(formatTonnes(0)).toBe('0.00 t')
    expect(formatPallets(0)).toBe('0 pallets')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatMinutes(0)).toBe('0 min')
  })
})

describe('formatting', () => {
  it('tonnes to 2 dp with thousands separators', () => {
    expect(formatTonnes(7.198)).toBe('7.20 t')
    expect(formatTonnes(1234.5)).toBe('1,234.50 t')
  })

  it('pallets up to 1 dp, singular for one', () => {
    expect(formatPallets(1)).toBe('1 pallet')
    expect(formatPallets(3.75)).toBe('3.8 pallets')
    expect(formatPallets(12)).toBe('12 pallets')
  })

  it('percent to 1 dp', () => {
    expect(formatPercent(84.56)).toBe('84.6%')
    expect(formatPercent(100)).toBe('100.0%')
  })

  it('minutes as minutes, or hours and minutes', () => {
    expect(formatMinutes(45.4)).toBe('45 min')
    expect(formatMinutes(59.6)).toBe('1 h 00 min')
    expect(formatMinutes(125)).toBe('2 h 05 min')
  })

  it('date-times in UK time across BST and GMT', () => {
    expect(formatDateTime('2026-09-25T09:30:00+00:00')).toContain('10:30')
    expect(formatDateTime('2026-12-01T09:30:00+00:00')).toContain('09:30')
    expect(formatDateTime(null)).toBe(MISSING)
    expect(formatDateTime('not-a-date')).toBe(MISSING)
  })

  it('calendar dates without any time-zone shift', () => {
    expect(formatCalendarDate('2026-09-01')).toMatch(/^1 Sept? 2026$/)
    expect(formatCalendarDate('2026-12-31')).toBe('31 Dec 2026')
    expect(formatCalendarDate(null)).toBe(MISSING)
  })

  it('takes the calendar date from a London-local timestamp as written', () => {
    expect(localDatePart('2026-09-21T06:00:00+01:00')).toBe('2026-09-21')
    expect(localDatePart('2026-09-21T23:30:00+01:00')).toBe('2026-09-21')
    expect(localDatePart(undefined)).toBeNull()
    expect(localDatePart('garbage')).toBeNull()
  })
})

describe('barWidthPercent (visual scale only)', () => {
  it('scales against the largest value and caps at 100', () => {
    expect(barWidthPercent(5, 10)).toBe(50)
    expect(barWidthPercent(10, 10)).toBe(100)
    expect(barWidthPercent(12, 10)).toBe(100)
  })

  it('draws nothing for zero, negative, missing or no scale', () => {
    expect(barWidthPercent(0, 10)).toBe(0)
    expect(barWidthPercent(-1, 10)).toBe(0)
    expect(barWidthPercent(null, 10)).toBe(0)
    expect(barWidthPercent(5, 0)).toBe(0)
  })
})

describe('calendar helpers', () => {
  it('adds days across month and year ends', async () => {
    const { addDays } = await import('./format')
    expect(addDays('2026-09-28', -7)).toBe('2026-09-21')
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31')
    expect(addDays('2026-02-28', 1)).toBe('2026-03-01')
  })

  it('reads today on the London clock, not UTC', async () => {
    const { londonToday } = await import('./format')
    // 23:30 UTC on 30 Sep is 00:30 BST on 1 Oct.
    expect(londonToday(new Date('2026-09-30T23:30:00Z'))).toBe('2026-10-01')
  })

  it('formats short dates, pack weights and counts without inventing values', async () => {
    const { formatShortDate, formatPackWeight, formatCount, MISSING } = await import('./format')
    expect(formatShortDate('2026-09-21')).toBe('21 Sep')
    expect(formatPackWeight(1)).toBe('1 kg')
    expect(formatPackWeight(0.5)).toBe('500 g')
    expect(formatPackWeight(null)).toBe(MISSING)
    expect(formatCount(undefined)).toBe(MISSING)
  })
})
