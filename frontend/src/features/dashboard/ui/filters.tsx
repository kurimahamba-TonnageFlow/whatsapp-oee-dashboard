import type { ReactNode } from 'react'

export function FilterBar({ label, children, note }: { label: string; children: ReactNode; note?: ReactNode }) {
  return (
    <>
      <form className="pd-filters" aria-label={label} onSubmit={(event) => event.preventDefault()}>
        {children}
      </form>
      {note && <p className="pd-filters__note">{note}</p>}
    </>
  )
}

interface SelectFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  options: ReadonlyArray<string | { value: string; label: string }>
  /** First option, value "" - e.g. "All Lines". Omit for a required choice. */
  allLabel?: string
}

export function SelectField({ label, value, onChange, options, allLabel }: SelectFieldProps) {
  return (
    <label className="pd-field">
      <span className="pd-field__label">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {allLabel !== undefined && <option value="">{allLabel}</option>}
        {options.map((option) => {
          const item = typeof option === 'string' ? { value: option, label: option } : option
          return (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          )
        })}
      </select>
    </label>
  )
}

export function DateField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="pd-field">
      <span className="pd-field__label">{label}</span>
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  )
}
