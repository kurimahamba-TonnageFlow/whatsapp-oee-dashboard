/**
 * Pack weight safety validation (Stage 4 fix).
 *
 * The Start Run form has two pack-weight fields that must agree:
 * a readable label (e.g. "500g", matching the existing CLI convention
 * in src/main.py's pack_sizes_by_line) and a numeric kg value used for
 * every downstream calculation (POST /api/v1/runs' pack_weight_kg,
 * and every tonnage figure derived from it on the Active Run screen
 * and in the Dashboard). If those two disagree, tonnage calculations
 * and dashboard reporting would be built on inconsistent data - this
 * module makes that impossible to submit.
 */

/** Sensible upper bound for a single retail pack (not a pallet). The
 * project's own configured pack sizes (src/main.py's
 * pack_sizes_by_line) top out at 4kg - 25kg leaves generous headroom
 * while still catching obvious data-entry mistakes. Adjustable. */
export const PACK_WEIGHT_MAX_KG = 25

const PACK_WEIGHT_LABEL_PATTERN = /^(\d+(?:\.\d+)?)\s*(kg|g)$/i

/**
 * Parses a pack weight label such as "500g", "1 kg", "0.5KG" into a
 * kilogram value. Case-insensitive; a single space between the number
 * and unit is allowed. Returns null if there is no recognised unit, no
 * valid number, or the number is not positive.
 */
export function parsePackWeightLabel(label: string): number | null {
  const match = PACK_WEIGHT_LABEL_PATTERN.exec(label.trim())
  if (!match) return null

  const amount = Number(match[1])
  if (!Number.isFinite(amount) || amount <= 0) return null

  const unit = match[2].toLowerCase()
  return unit === 'g' ? amount / 1000 : amount
}

/** Formats a kg value for display/messages, trimming trailing zeros
 * (e.g. "0.5", not "0.500"). */
export function formatKg(value: number): string {
  return Number(value.toFixed(3)).toString()
}

export interface PackWeightValidation {
  error: string | null
  convertedKg: number | null
}

const MATCH_TOLERANCE_KG = 0.001

/**
 * Cross-validates the operator-entered pack weight label against the
 * numeric "Pack weight (kg)" field. Both must be present, the label
 * must parse to a realistic weight, the kg field must be a realistic
 * positive number, and the two must agree - otherwise this returns a
 * single, plain-language error suitable for display beside either
 * field.
 */
export function validatePackWeight(label: string, kgValue: string): PackWeightValidation {
  const trimmedLabel = label.trim()

  if (trimmedLabel === '') {
    return { error: 'Required.', convertedKg: null }
  }

  const convertedKg = parsePackWeightLabel(trimmedLabel)
  if (convertedKg === null) {
    return {
      error: `"${trimmedLabel}" is not a recognised pack weight. Use a format such as 500g or 1kg.`,
      convertedKg: null,
    }
  }

  if (convertedKg > PACK_WEIGHT_MAX_KG) {
    return {
      error: `${trimmedLabel} (${formatKg(convertedKg)} kg) is not a realistic pack weight.`,
      convertedKg,
    }
  }

  const trimmedKg = kgValue.trim()
  if (trimmedKg === '') {
    return { error: 'Required.', convertedKg }
  }

  const kgNumber = Number(trimmedKg)
  if (!Number.isFinite(kgNumber) || kgNumber <= 0) {
    return { error: 'Enter a pack weight (kg) greater than 0.', convertedKg }
  }

  // Checked before the realism check below: a value that disagrees with
  // the label is a data-entry mismatch first, and only actually "unrealistic"
  // in its own right once it also agrees with the label (see the tests) -
  // "does not match, expected X" is more actionable than "not realistic".
  if (Math.abs(kgNumber - convertedKg) > MATCH_TOLERANCE_KG) {
    return {
      error: `Pack weight does not match. ${trimmedLabel} must equal ${formatKg(convertedKg)} kg.`,
      convertedKg,
    }
  }

  if (kgNumber > PACK_WEIGHT_MAX_KG) {
    return { error: `${kgNumber} kg is not a realistic pack weight.`, convertedKg }
  }

  return { error: null, convertedKg }
}
