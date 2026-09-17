import { describe, expect, it } from 'vitest'
import { parsePackWeightLabel, validatePackWeight } from './packWeight'

describe('parsePackWeightLabel', () => {
  it('parses "500g" as 0.5 kg', () => {
    expect(parsePackWeightLabel('500g')).toBe(0.5)
  })

  it('parses "500 g" (with a space) as 0.5 kg', () => {
    expect(parsePackWeightLabel('500 g')).toBe(0.5)
  })

  it('parses "1kg" as 1 kg', () => {
    expect(parsePackWeightLabel('1kg')).toBe(1)
  })

  it('parses "2 kg" as 2 kg', () => {
    expect(parsePackWeightLabel('2 kg')).toBe(2)
  })

  it('parses "750g" as 0.75 kg', () => {
    expect(parsePackWeightLabel('750g')).toBe(0.75)
  })

  it('accepts uppercase units', () => {
    expect(parsePackWeightLabel('500G')).toBe(0.5)
    expect(parsePackWeightLabel('1KG')).toBe(1)
  })

  it('returns null for text with no recognised unit', () => {
    expect(parsePackWeightLabel('500')).toBeNull()
  })

  it('returns null for invalid text', () => {
    expect(parsePackWeightLabel('heavy')).toBeNull()
    expect(parsePackWeightLabel('')).toBeNull()
  })

  it('returns null for zero or negative amounts', () => {
    expect(parsePackWeightLabel('0kg')).toBeNull()
    expect(parsePackWeightLabel('-1kg')).toBeNull()
  })
})

describe('validatePackWeight', () => {
  it('passes when 500g matches 0.5 kg', () => {
    expect(validatePackWeight('500g', '0.5')).toEqual({ error: null, convertedKg: 0.5 })
  })

  it('passes when "500 g" matches 0.5 kg', () => {
    expect(validatePackWeight('500 g', '0.5')).toEqual({ error: null, convertedKg: 0.5 })
  })

  it('passes when 1kg matches 1 kg', () => {
    expect(validatePackWeight('1kg', '1')).toEqual({ error: null, convertedKg: 1 })
  })

  it('passes when 2kg matches 2 kg', () => {
    expect(validatePackWeight('2kg', '2')).toEqual({ error: null, convertedKg: 2 })
  })

  it('passes with uppercase units', () => {
    expect(validatePackWeight('1KG', '1').error).toBeNull()
    expect(validatePackWeight('500G', '0.5').error).toBeNull()
  })

  it('blocks 500g against 500 kg with a clear mismatch message', () => {
    const result = validatePackWeight('500g', '500')
    expect(result.error).toBe('Pack weight does not match. 500g must equal 0.5 kg.')
  })

  it('blocks a value with no unit', () => {
    const result = validatePackWeight('500', '0.5')
    expect(result.error).toMatch(/not a recognised pack weight/i)
  })

  it('blocks invalid text', () => {
    const result = validatePackWeight('heavy', '1')
    expect(result.error).toMatch(/not a recognised pack weight/i)
  })

  it('blocks a zero or negative kg value even when the label is valid', () => {
    expect(validatePackWeight('1kg', '0').error).toMatch(/greater than 0/i)
    expect(validatePackWeight('1kg', '-1').error).toMatch(/greater than 0/i)
  })

  it('blocks an unrealistic kg value', () => {
    const result = validatePackWeight('30kg', '30')
    expect(result.error).toMatch(/not a realistic pack weight/i)
  })

  it('requires both fields', () => {
    expect(validatePackWeight('', '1').error).toBe('Required.')
    expect(validatePackWeight('1kg', '').error).toBe('Required.')
  })
})
