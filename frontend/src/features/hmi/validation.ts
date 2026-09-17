import { validatePackWeight } from './packWeight'
import type { StartRunFormValues } from './types'

export type StartRunFormErrors = Partial<Record<keyof StartRunFormValues, string>>

// packWeightLabel is deliberately not in this list - it has its own
// dedicated cross-validation against packWeightKg below (which also
// covers "Required.") so the two pack-weight fields are never
// validated independently of each other.
const REQUIRED_TEXT_FIELDS: Array<keyof StartRunFormValues> = [
  'productionLine',
  'lineTechnician',
  'shift',
  'customer',
  'product',
  'packType',
]

function isBlank(value: string): boolean {
  return value.trim().length === 0
}

/** Blank shows "Required."; a filled-in but non-positive value shows
 * the field-specific message - the two are never conflated. */
function validatePositive(value: string, invalidMessage: string): string | null {
  if (isBlank(value)) return 'Required.'
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return invalidMessage
  return null
}

/** Same as validatePositive, but zero is a valid value - only a
 * filled-in negative (or non-numeric) value is rejected. */
function validateNonNegative(value: string, invalidMessage: string): string | null {
  if (isBlank(value)) return 'Required.'
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) return invalidMessage
  return null
}

/** Validates the Start Run form. Every message is short and plain, and
 * is displayed beside its field (see screens/StartRunFormScreen.tsx). */
export function validateStartRunForm(values: StartRunFormValues): StartRunFormErrors {
  const errors: StartRunFormErrors = {}

  for (const field of REQUIRED_TEXT_FIELDS) {
    if (isBlank(values[field])) {
      errors[field] = 'Required.'
    }
  }

  const packWeight = validatePackWeight(values.packWeightLabel, values.packWeightKg)
  if (packWeight.error) {
    // Shown beside both fields - the operator may be looking at
    // either one when the mismatch is the actual problem.
    errors.packWeightLabel = packWeight.error
    errors.packWeightKg = packWeight.error
  }

  const packsPerCaseError = validatePositive(
    values.packsPerCase,
    'Enter packs per case greater than 0.',
  )
  if (packsPerCaseError) errors.packsPerCase = packsPerCaseError

  const targetSpeedError = validatePositive(
    values.targetSpeedPpm,
    'Enter a target speed greater than 0.',
  )
  if (targetSpeedError) errors.targetSpeedPpm = targetSpeedError

  const casesPerPalletError = validatePositive(
    values.casesPerPallet,
    'Enter cases per pallet greater than 0.',
  )
  if (casesPerPalletError) errors.casesPerPallet = casesPerPalletError

  const palletsRemainingError = validateNonNegative(
    values.palletsRemaining,
    'Pallets remaining cannot be negative.',
  )
  if (palletsRemainingError) errors.palletsRemaining = palletsRemainingError

  const previousRunCompletedError = validateNonNegative(
    values.previousRunCompleted,
    'Cannot be negative.',
  )
  if (previousRunCompletedError) errors.previousRunCompleted = previousRunCompletedError

  return errors
}

export function hasStartRunFormErrors(errors: StartRunFormErrors): boolean {
  return Object.keys(errors).length > 0
}
