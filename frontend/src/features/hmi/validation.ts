import { validatePackWeight } from './packWeight'
import type { CompleteRunFormValues, StartRunFormValues } from './types'

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

// ------------------------------------------------------------
// Capture inputs (hourly update, changeover, Complete Run)
// ------------------------------------------------------------
// These mirror the backend's own rules (src/pulse_capture_api.py) but
// never replace them - FastAPI validates every request again.

const DECIMAL_PATTERN = /^\d+(\.\d{1,4})?$/
const WHOLE_NUMBER_PATTERN = /^\d+$/

/** Pallets are decimal-safe: "3.75" is valid, "0" is valid (the line
 * produced nothing), anything negative or non-numeric is not. */
export function validatePalletsInput(
  value: string,
  options: { allowZero?: boolean } = {},
): string | undefined {
  const { allowZero = true } = options
  const trimmed = value.trim()

  if (isBlank(trimmed)) return 'Enter the pallets produced, for example 3.75.'
  if (!DECIMAL_PATTERN.test(trimmed)) {
    return 'Enter pallets as a number with up to 4 decimal places, for example 3.75.'
  }
  if (Number(trimmed) > 1000) return 'That is more than 1000 pallets - check the figure.'
  if (!allowZero && Number(trimmed) === 0) return 'Enter the pallets produced since the last update.'

  return undefined
}

export function validateXrayCountInput(value: string): string | undefined {
  const trimmed = value.trim()

  if (isBlank(trimmed)) return 'Enter the X-ray pack count, or select Count unavailable.'
  if (!WHOLE_NUMBER_PATTERN.test(trimmed)) return 'Enter the X-ray pack count as a whole number.'
  if (Number(trimmed) > 10_000_000) return 'That count looks too high - check the figure.'

  return undefined
}

export function validatePackWeightInput(value: string): string | undefined {
  const trimmed = value.trim()

  if (isBlank(trimmed)) return 'Enter the new pack weight in kg.'
  if (!DECIMAL_PATTERN.test(trimmed)) return 'Enter the pack weight in kg, for example 1 or 4.5.'
  if (Number(trimmed) <= 0) return 'Pack weight must be more than zero.'

  return undefined
}

export function validateRequiredText(value: string, label: string): string | undefined {
  return isBlank(value) ? `${label} is required.` : undefined
}

/** Complete Run needs the final production answer before anything else:
 * any output made since the last hourly update has to be captured
 * before the X-ray count can be compared against it. */
export function completeRunFormErrors(values: CompleteRunFormValues) {
  const errors: Partial<Record<keyof CompleteRunFormValues, string>> = {}

  if (values.productionSinceLastUpdate === '') {
    errors.productionSinceLastUpdate =
      'Answer whether anything has been produced since the last update.'
  }

  if (values.productionSinceLastUpdate === 'yes') {
    const palletsError = validatePalletsInput(values.finalPallets, { allowZero: false })
    if (palletsError) errors.finalPallets = palletsError
  }

  if (values.countUnavailable) {
    if (!values.unavailableReason.trim()) {
      errors.unavailableReason = 'Give a reason why the X-ray count is unavailable.'
    }
  } else {
    const countError = validateXrayCountInput(values.xrayPackCount)
    if (countError) errors.xrayPackCount = countError
  }

  return errors
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
