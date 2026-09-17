import { describe, expect, it } from 'vitest'
import { EMPTY_START_RUN_FORM } from './types'
import { hasStartRunFormErrors, validateStartRunForm } from './validation'

const VALID_FORM = {
  ...EMPTY_START_RUN_FORM,
  productionLine: 'Rovema',
  lineTechnician: 'Liam',
  shift: 'Days',
  customer: 'Asda',
  product: 'White Basmati',
  packWeightLabel: '1kg',
  packWeightKg: '1',
  packsPerCase: '8',
  packType: '1 kg × 8',
  targetSpeedPpm: '120',
  casesPerPallet: '220',
  palletsRemaining: '38',
  previousRunCompleted: '0',
}

describe('validateStartRunForm', () => {
  it('accepts a fully valid form', () => {
    expect(hasStartRunFormErrors(validateStartRunForm(VALID_FORM))).toBe(false)
  })

  it('rejects blank required text fields', () => {
    const errors = validateStartRunForm({ ...VALID_FORM, customer: '   ' })
    expect(errors.customer).toBeTruthy()
  })

  it('rejects a non-positive pack weight', () => {
    expect(validateStartRunForm({ ...VALID_FORM, packWeightKg: '0' }).packWeightKg).toBeTruthy()
    expect(validateStartRunForm({ ...VALID_FORM, packWeightKg: '-1' }).packWeightKg).toBeTruthy()
  })

  it('shows "Required." for a blank pack weight (kg), not the greater-than-0 message', () => {
    expect(validateStartRunForm({ ...VALID_FORM, packWeightKg: '' }).packWeightKg).toBe(
      'Required.',
    )
  })

  it('rejects a non-positive packs per case', () => {
    expect(validateStartRunForm({ ...VALID_FORM, packsPerCase: '0' }).packsPerCase).toBeTruthy()
    expect(validateStartRunForm({ ...VALID_FORM, packsPerCase: '-1' }).packsPerCase).toBeTruthy()
  })

  it('shows "Required." for a blank packs per case, not the greater-than-0 message', () => {
    expect(validateStartRunForm({ ...VALID_FORM, packsPerCase: '' }).packsPerCase).toBe(
      'Required.',
    )
  })

  it('rejects a non-positive target speed', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, targetSpeedPpm: '0' }).targetSpeedPpm,
    ).toBeTruthy()
    expect(
      validateStartRunForm({ ...VALID_FORM, targetSpeedPpm: '-1' }).targetSpeedPpm,
    ).toBeTruthy()
  })

  it('shows "Required." for a blank target speed, not the greater-than-0 message', () => {
    expect(validateStartRunForm({ ...VALID_FORM, targetSpeedPpm: '' }).targetSpeedPpm).toBe(
      'Required.',
    )
  })

  it('rejects a non-positive cases per pallet', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, casesPerPallet: '0' }).casesPerPallet,
    ).toBeTruthy()
    expect(
      validateStartRunForm({ ...VALID_FORM, casesPerPallet: '-1' }).casesPerPallet,
    ).toBeTruthy()
  })

  it('shows "Required." for a blank cases per pallet, not the greater-than-0 message', () => {
    expect(validateStartRunForm({ ...VALID_FORM, casesPerPallet: '' }).casesPerPallet).toBe(
      'Required.',
    )
  })

  it('rejects negative pallets remaining', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, palletsRemaining: '-1' }).palletsRemaining,
    ).toBeTruthy()
  })

  it('accepts zero pallets remaining', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, palletsRemaining: '0' }).palletsRemaining,
    ).toBeUndefined()
  })

  it('shows "Required." for a blank pallets remaining, not the cannot-be-negative message', () => {
    expect(validateStartRunForm({ ...VALID_FORM, palletsRemaining: '' }).palletsRemaining).toBe(
      'Required.',
    )
  })

  it('rejects negative previous run completed', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, previousRunCompleted: '-1' }).previousRunCompleted,
    ).toBeTruthy()
  })

  it('accepts zero previous run completed', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, previousRunCompleted: '0' }).previousRunCompleted,
    ).toBeUndefined()
  })

  it('shows "Required." for a blank previous run completed', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, previousRunCompleted: '' }).previousRunCompleted,
    ).toBe('Required.')
  })

  it('accepts the format example "1×10"', () => {
    expect(
      validateStartRunForm({ ...VALID_FORM, packType: '1×10' }).packType,
    ).toBeUndefined()
  })
})
