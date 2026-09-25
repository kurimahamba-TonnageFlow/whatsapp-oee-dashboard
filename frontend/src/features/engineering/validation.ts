/**
 * Mirrors src/engineering_api.py's RepairUpdateRequest validation
 * exactly: finding/action required and trimmed; Machine Setting
 * fields all required when that classification is selected, all
 * rejected (must be blank) for Mechanical. Browser-side only - never
 * a substitute for the backend's own validation, which always runs
 * again server-side.
 */
import { MAX_HANDOVER_NOTE_LENGTH, MAX_REASON_LENGTH, MAX_SHORT_FIELD_LENGTH, MAX_TEXT_LENGTH } from './constants'
import type { MaintenancePreventable, RepairClassification } from './types'

/** 'update' = interim repair update; 'close' additionally requires the
 * maintenance-preventability answer. */
export type RepairFormMode = 'update' | 'close'

export interface RepairUpdateFormValues {
  classification: RepairClassification | ''
  finding: string
  action: string
  notes: string
  settingName: string
  previousValue: string
  newValue: string
  reasonForChange: string
  affectedProductsOrFormats: string
  /** Empty until the engineer deliberately chooses - never preselected. */
  maintenancePreventable: MaintenancePreventable | ''
}

export const EMPTY_REPAIR_UPDATE_FORM: RepairUpdateFormValues = {
  classification: '',
  finding: '',
  action: '',
  notes: '',
  settingName: '',
  previousValue: '',
  newValue: '',
  reasonForChange: '',
  affectedProductsOrFormats: '',
  maintenancePreventable: '',
}

export interface RepairUpdateFormErrors {
  maintenancePreventable?: string
  classification?: string
  finding?: string
  action?: string
  notes?: string
  settingName?: string
  previousValue?: string
  newValue?: string
  reasonForChange?: string
  affectedProductsOrFormats?: string
}

function requiredText(value: string, maxLength: number, label: string): string | undefined {
  const trimmed = value.trim()
  if (!trimmed) return `${label} is required.`
  if (trimmed.length > maxLength) return `${label} must be ${maxLength} characters or fewer.`
  return undefined
}

function optionalText(value: string, maxLength: number, label: string): string | undefined {
  const trimmed = value.trim()
  if (trimmed.length > maxLength) return `${label} must be ${maxLength} characters or fewer.`
  return undefined
}

export function validateRepairUpdateForm(
  values: RepairUpdateFormValues,
  mode: RepairFormMode = 'update',
): RepairUpdateFormErrors {
  const errors: RepairUpdateFormErrors = {}

  if (!values.classification) {
    errors.classification = 'Select Mechanical or Machine Setting.'
  }

  if (mode === 'close' && !values.maintenancePreventable) {
    errors.maintenancePreventable =
      'Answer whether planned maintenance could have prevented this fault.'
  }

  const findingError = requiredText(values.finding, MAX_TEXT_LENGTH, 'Finding')
  if (findingError) errors.finding = findingError

  const actionError = requiredText(values.action, MAX_TEXT_LENGTH, 'Action taken')
  if (actionError) errors.action = actionError

  const notesError = optionalText(values.notes, MAX_TEXT_LENGTH, 'Notes')
  if (notesError) errors.notes = notesError

  if (values.classification === 'Machine Setting') {
    const settingNameError = requiredText(values.settingName, MAX_SHORT_FIELD_LENGTH, 'Setting name')
    if (settingNameError) errors.settingName = settingNameError

    const previousValueError = requiredText(values.previousValue, MAX_SHORT_FIELD_LENGTH, 'Previous value')
    if (previousValueError) errors.previousValue = previousValueError

    const newValueError = requiredText(values.newValue, MAX_SHORT_FIELD_LENGTH, 'New value')
    if (newValueError) errors.newValue = newValueError

    const reasonError = requiredText(values.reasonForChange, MAX_REASON_LENGTH, 'Reason for change')
    if (reasonError) errors.reasonForChange = reasonError

    const affectedError = requiredText(
      values.affectedProductsOrFormats,
      MAX_REASON_LENGTH,
      'Affected products or formats',
    )
    if (affectedError) errors.affectedProductsOrFormats = affectedError
  }

  return errors
}

export function hasFormErrors(errors: RepairUpdateFormErrors): boolean {
  return Object.values(errors).some((message) => message !== undefined)
}

/** Converts validated, trimmed form values into the exact API request
 * body shape - Machine Setting fields are omitted (not blank strings)
 * for a Mechanical update, matching the backend's "must not include
 * Machine Setting fields" rule. */
export function toRepairUpdatePayload(
  values: RepairUpdateFormValues,
  mode: RepairFormMode = 'update',
) {
  const classification = values.classification as RepairClassification

  const base = {
    classification,
    finding: values.finding.trim(),
    action: values.action.trim(),
    notes: values.notes.trim() || null,
    ...(mode === 'close'
      ? { maintenance_preventable: values.maintenancePreventable as MaintenancePreventable }
      : {}),
  }

  if (classification !== 'Machine Setting') {
    return base
  }

  return {
    ...base,
    setting_name: values.settingName.trim(),
    previous_value: values.previousValue.trim(),
    new_value: values.newValue.trim(),
    reason_for_change: values.reasonForChange.trim(),
    affected_products_or_formats: values.affectedProductsOrFormats.trim(),
  }
}

/** Mirrors src/engineering_api.py's HandoverRequest validation: a
 * required, trimmed, non-blank note up to MAX_HANDOVER_NOTE_LENGTH. */
export function validateHandoverNote(note: string): string | undefined {
  return requiredText(note, MAX_HANDOVER_NOTE_LENGTH, 'Handover note')
}
