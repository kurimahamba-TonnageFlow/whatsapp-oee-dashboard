import { parsePackFormat } from '../packWeight'
import { StandardPreview } from '../components/StandardPreview'
import type { FormEvent } from 'react'
import { CUSTOMERS, LINE_TECHNICIANS, PRODUCTS, SHIFTS } from '../constants'
import { FieldError } from '../components/FieldError'
import type { StartRunFormErrors } from '../validation'
import type { StartRunFormValues } from '../types'

interface StartRunFormScreenProps {
  values: StartRunFormValues
  errors: StartRunFormErrors
  onChange: (field: keyof StartRunFormValues, value: string) => void
  onBack: () => void
  onClear: () => void
  onReview: () => void
  /** A handover / changeover still timing on the line until this run starts. */
  timerNotice?: string | null
}

export function StartRunFormScreen({
  values,
  errors,
  onChange,
  onBack,
  onClear,
  onReview,
  timerNotice = null,
}: StartRunFormScreenProps) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onReview()
  }

  return (
    <div className="hmi-screen hmi-start-run-form">
      <h1>Start Run — {values.productionLine}</h1>
      {timerNotice && (
        <p className="hmi-timer-notice" role="status">
          ⏱ {timerNotice}
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="hmi-form-grid">
          <label className="hmi-field">
            Line technician
            <select
              value={values.lineTechnician}
              onChange={(e) => onChange('lineTechnician', e.target.value)}
            >
              <option value="">Select…</option>
              {LINE_TECHNICIANS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <FieldError message={errors.lineTechnician} />
          </label>

          <label className="hmi-field">
            Shift
            <select value={values.shift} onChange={(e) => onChange('shift', e.target.value)}>
              <option value="">Select…</option>
              {SHIFTS.map((shift) => (
                <option key={shift.name} value={shift.name}>
                  {shift.label}
                </option>
              ))}
            </select>
            <FieldError message={errors.shift} />
          </label>

          <label className="hmi-field">
            Customer
            <select value={values.customer} onChange={(e) => onChange('customer', e.target.value)}>
              <option value="">Select…</option>
              {CUSTOMERS.map((customer) => (
                <option key={customer} value={customer}>
                  {customer}
                </option>
              ))}
            </select>
            <FieldError message={errors.customer} />
          </label>

          <label className="hmi-field">
            Product
            <select value={values.product} onChange={(e) => onChange('product', e.target.value)}>
              <option value="">Select…</option>
              {PRODUCTS.map((product) => (
                <option key={product} value={product}>
                  {product}
                </option>
              ))}
            </select>
            <FieldError message={errors.product} />
          </label>

          <label className="hmi-field">
            Pack weight (e.g. 1kg, 500g)
            <input
              type="text"
              value={values.packWeightLabel}
              onChange={(e) => onChange('packWeightLabel', e.target.value)}
            />
            <FieldError message={errors.packWeightLabel || errors.packWeightKg} />
          </label>

          <label className="hmi-field">
            Format (e.g. 1 kg × 8, 1×10)
            <input
              type="text"
              value={values.packType}
              onChange={(e) => onChange('packType', e.target.value)}
            />
            <FieldError message={errors.packType || (values.packType ? parsePackFormat(values.packType, values.packWeightLabel).error ?? errors.packsPerCase : errors.packsPerCase)} />
          </label>

          <StandardPreview values={values} />
          <p className="hmi-field-help">The management standard is fixed when the run starts. Pack weight and packs per case are calculated from your entries.</p>

          <label className="hmi-field">
            Cases per pallet
            <input
              type="number"
              inputMode="numeric"
              step="1"
              value={values.casesPerPallet}
              onChange={(e) => onChange('casesPerPallet', e.target.value)}
            />
            <FieldError message={errors.casesPerPallet} />
          </label>

          <label className="hmi-field">
            Pallets remaining
            <input
              type="number"
              inputMode="numeric"
              step="1"
              value={values.palletsRemaining}
              onChange={(e) => onChange('palletsRemaining', e.target.value)}
            />
            <FieldError message={errors.palletsRemaining} />
          </label>

          <label className="hmi-field">
            Previous run completed (pallets)
            <input
              type="number"
              inputMode="numeric"
              step="1"
              value={values.previousRunCompleted}
              onChange={(e) => onChange('previousRunCompleted', e.target.value)}
            />
            <FieldError message={errors.previousRunCompleted} />
          </label>
        </div>

        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onBack}>
            Back
          </button>
          <button type="button" className="hmi-secondary-button" onClick={onClear}>
            Clear
          </button>
          <button type="submit" className="hmi-primary-button">
            Review Run
          </button>
        </div>
      </form>
    </div>
  )
}
