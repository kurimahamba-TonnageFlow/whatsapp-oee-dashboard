import { useEffect, useState } from 'react'
import { FieldError } from './FieldError'
import { REPAIR_CLASSIFICATIONS, MAX_TEXT_LENGTH, MAX_SHORT_FIELD_LENGTH, MAX_REASON_LENGTH } from './constants'
import {
  EMPTY_REPAIR_UPDATE_FORM,
  hasFormErrors,
  toRepairUpdatePayload,
  validateRepairUpdateForm,
  type RepairUpdateFormValues,
} from './validation'
import type { RepairUpdatePayload } from './types'

interface RepairUpdateFormProps {
  /** "Add Repair Update" for /updates, "Close Fault" for /close - only
   * the submit button label, confirmation copy and outer flow differ;
   * the fields and validation are identical either way. */
  mode: 'update' | 'close'
  isSubmitting: boolean
  onSubmit: (payload: RepairUpdatePayload) => void
  /** Bump this (e.g. a counter) once the parent confirms FastAPI
   * accepted the submission - clears the form only at that point,
   * never on a failed submission (entered text must survive a
   * failure so the engineer doesn't have to retype it). */
  resetSignal?: number
}

export function RepairUpdateForm({ mode, isSubmitting, onSubmit, resetSignal }: RepairUpdateFormProps) {
  const [values, setValues] = useState<RepairUpdateFormValues>(EMPTY_REPAIR_UPDATE_FORM)
  const [errors, setErrors] = useState(validateRepairUpdateForm(EMPTY_REPAIR_UPDATE_FORM))
  const [touched, setTouched] = useState(false)

  useEffect(() => {
    if (resetSignal === undefined) return
    setValues(EMPTY_REPAIR_UPDATE_FORM)
    setErrors(validateRepairUpdateForm(EMPTY_REPAIR_UPDATE_FORM))
    setTouched(false)
  }, [resetSignal])

  function setField<K extends keyof RepairUpdateFormValues>(key: K, value: RepairUpdateFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setTouched(true)

    const validationErrors = validateRepairUpdateForm(values)
    setErrors(validationErrors)

    if (hasFormErrors(validationErrors) || isSubmitting) return

    onSubmit(toRepairUpdatePayload(values) as RepairUpdatePayload)
  }

  const isMachineSetting = values.classification === 'Machine Setting'
  const submitLabel = mode === 'close' ? 'Close Fault' : 'Add Repair Update'

  return (
    <form className="engineering-repair-form" onSubmit={handleSubmit} noValidate>
      <fieldset>
        <legend>Repair classification *</legend>
        <div className="engineering-radio-group">
          {REPAIR_CLASSIFICATIONS.map((option) => (
            <label key={option} className="engineering-radio">
              <input
                type="radio"
                name="repair-classification"
                value={option}
                checked={values.classification === option}
                onChange={() => setField('classification', option)}
              />
              {option}
            </label>
          ))}
        </div>
        {touched && <FieldError message={errors.classification} />}
      </fieldset>

      <label className="engineering-field">
        Finding *
        <textarea
          value={values.finding}
          onChange={(event) => setField('finding', event.target.value)}
          maxLength={MAX_TEXT_LENGTH}
          rows={3}
          required
        />
        {touched && <FieldError message={errors.finding} />}
      </label>

      <label className="engineering-field">
        Action taken *
        <textarea
          value={values.action}
          onChange={(event) => setField('action', event.target.value)}
          maxLength={MAX_TEXT_LENGTH}
          rows={3}
          required
        />
        {touched && <FieldError message={errors.action} />}
      </label>

      <label className="engineering-field">
        Notes (optional)
        <textarea
          value={values.notes}
          onChange={(event) => setField('notes', event.target.value)}
          maxLength={MAX_TEXT_LENGTH}
          rows={2}
        />
        {touched && <FieldError message={errors.notes} />}
      </label>

      {isMachineSetting && (
        <div className="engineering-machine-setting-fields">
          <label className="engineering-field">
            Setting name *
            <input
              type="text"
              value={values.settingName}
              onChange={(event) => setField('settingName', event.target.value)}
              maxLength={MAX_SHORT_FIELD_LENGTH}
              required
            />
            {touched && <FieldError message={errors.settingName} />}
          </label>

          <label className="engineering-field">
            Previous value *
            <input
              type="text"
              value={values.previousValue}
              onChange={(event) => setField('previousValue', event.target.value)}
              maxLength={MAX_SHORT_FIELD_LENGTH}
              required
            />
            {touched && <FieldError message={errors.previousValue} />}
          </label>

          <label className="engineering-field">
            New value *
            <input
              type="text"
              value={values.newValue}
              onChange={(event) => setField('newValue', event.target.value)}
              maxLength={MAX_SHORT_FIELD_LENGTH}
              required
            />
            {touched && <FieldError message={errors.newValue} />}
          </label>

          <label className="engineering-field">
            Reason for change *
            <textarea
              value={values.reasonForChange}
              onChange={(event) => setField('reasonForChange', event.target.value)}
              maxLength={MAX_REASON_LENGTH}
              rows={2}
              required
            />
            {touched && <FieldError message={errors.reasonForChange} />}
          </label>

          <label className="engineering-field">
            Affected products or formats *
            <textarea
              value={values.affectedProductsOrFormats}
              onChange={(event) => setField('affectedProductsOrFormats', event.target.value)}
              maxLength={MAX_REASON_LENGTH}
              rows={2}
              required
            />
            {touched && <FieldError message={errors.affectedProductsOrFormats} />}
          </label>
        </div>
      )}

      <div className="engineering-form-actions">
        <button
          type="submit"
          className={mode === 'close' ? 'engineering-danger-button' : 'engineering-primary-button'}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
