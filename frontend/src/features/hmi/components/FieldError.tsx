interface FieldErrorProps {
  message?: string
}

/** Shown directly beside the field it applies to. */
export function FieldError({ message }: FieldErrorProps) {
  if (!message) return null
  return (
    <span className="hmi-field-error" role="alert">
      {message}
    </span>
  )
}
