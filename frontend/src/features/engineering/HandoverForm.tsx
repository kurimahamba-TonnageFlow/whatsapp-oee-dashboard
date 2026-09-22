import { useEffect, useState } from 'react'
import { FieldError } from './FieldError'
import { MAX_HANDOVER_NOTE_LENGTH } from './constants'
import { validateHandoverNote } from './validation'

interface HandoverFormProps {
  isSubmitting: boolean
  /** Called once the note passes validation - this only advances to the
   * confirmation step (see FaultDetailPanel), it never calls the API
   * directly. */
  onSubmit: (note: string) => void
  /** Bump this once the parent confirms FastAPI accepted the handover -
   * clears the form only then, never on a failed/cancelled attempt. */
  resetSignal?: number
}

export function HandoverForm({ isSubmitting, onSubmit, resetSignal }: HandoverFormProps) {
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)

  useEffect(() => {
    if (resetSignal === undefined) return
    setNote('')
    setTouched(false)
  }, [resetSignal])

  const error = touched ? validateHandoverNote(note) : undefined

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setTouched(true)

    const validationError = validateHandoverNote(note)
    if (validationError || isSubmitting) return

    onSubmit(note.trim())
  }

  return (
    <form className="engineering-handover-form" onSubmit={handleSubmit} noValidate>
      <label className="engineering-field">
        Handover note *
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={MAX_HANDOVER_NOTE_LENGTH}
          rows={3}
          required
        />
        {touched && <FieldError message={error} />}
      </label>

      <div className="engineering-form-actions">
        <button type="submit" className="engineering-primary-button" disabled={isSubmitting}>
          {isSubmitting ? 'Please wait…' : 'Hand Over Job'}
        </button>
      </div>
    </form>
  )
}
