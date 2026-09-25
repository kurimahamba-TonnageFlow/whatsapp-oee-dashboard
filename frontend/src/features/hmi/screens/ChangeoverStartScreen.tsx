import { useState } from 'react'
import { CUSTOMERS, PRODUCTS } from '../constants'
import { validatePackWeightInput, validateRequiredText } from '../validation'
import type { ChangeoverFormValues, RunState } from '../types'

interface ChangeoverStartScreenProps {
  state: RunState
  values: ChangeoverFormValues
  isSubmitting: boolean
  errorMessage: string | null
  onChange: (field: keyof ChangeoverFormValues, value: string) => void
  onCancel: () => void
  onStart: () => void
}

export function ChangeoverStartScreen({
  state,
  values,
  isSubmitting,
  errorMessage,
  onChange,
  onCancel,
  onStart,
}: ChangeoverStartScreenProps) {
  const [touched, setTouched] = useState(false)

  const errors = {
    newCustomer: validateRequiredText(values.newCustomer, 'New customer'),
    newProduct: validateRequiredText(values.newProduct, 'New product'),
    newPackWeightKg: validatePackWeightInput(values.newPackWeightKg),
    newFormat: validateRequiredText(values.newFormat, 'New format'),
  }
  const hasErrors = Object.values(errors).some(Boolean)

  function handleStart() {
    setTouched(true)
    if (hasErrors) return
    onStart()
  }

  return (
    <div className="hmi-screen hmi-changeover">
      <h1>Start Changeover — {state.run.production_line}</h1>
      <p>
        This starts planned downtime and records the changeover together. Complete it when the
        first acceptable packs of the new run are produced.
      </p>

      <h2>Changing from</h2>
      <dl className="hmi-review-list">
        <div className="hmi-review-list__row">
          <dt>Customer</dt>
          <dd>{state.run.customer}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Product</dt>
          <dd>{state.run.product}</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Pack weight</dt>
          <dd>{state.run.pack_weight_kg} kg</dd>
        </div>
        <div className="hmi-review-list__row">
          <dt>Format</dt>
          <dd>{state.run.format ?? state.run.pack_type}</dd>
        </div>
      </dl>

      <h2>Changing to</h2>

      <label className="hmi-field">
        New customer
        <input
          list="hmi-changeover-customers"
          type="text"
          value={values.newCustomer}
          onChange={(e) => onChange('newCustomer', e.target.value)}
          disabled={isSubmitting}
        />
        <datalist id="hmi-changeover-customers">
          {CUSTOMERS.map((customer) => (
            <option key={customer} value={customer} />
          ))}
        </datalist>
        {touched && errors.newCustomer && (
          <span className="hmi-field-error" role="alert">
            {errors.newCustomer}
          </span>
        )}
      </label>

      <label className="hmi-field">
        New product or rice type
        <input
          list="hmi-changeover-products"
          type="text"
          value={values.newProduct}
          onChange={(e) => onChange('newProduct', e.target.value)}
          disabled={isSubmitting}
        />
        <datalist id="hmi-changeover-products">
          {PRODUCTS.map((product) => (
            <option key={product} value={product} />
          ))}
        </datalist>
        {touched && errors.newProduct && (
          <span className="hmi-field-error" role="alert">
            {errors.newProduct}
          </span>
        )}
      </label>

      <label className="hmi-field">
        New pack weight (kg)
        <input
          type="text"
          inputMode="decimal"
          value={values.newPackWeightKg}
          onChange={(e) => onChange('newPackWeightKg', e.target.value)}
          disabled={isSubmitting}
        />
        {touched && errors.newPackWeightKg && (
          <span className="hmi-field-error" role="alert">
            {errors.newPackWeightKg}
          </span>
        )}
      </label>

      <label className="hmi-field">
        New format
        <input
          type="text"
          value={values.newFormat}
          onChange={(e) => onChange('newFormat', e.target.value)}
          disabled={isSubmitting}
        />
        {touched && errors.newFormat && (
          <span className="hmi-field-error" role="alert">
            {errors.newFormat}
          </span>
        )}
      </label>

      <label className="hmi-field">
        Note (optional)
        <textarea
          value={values.note}
          onChange={(e) => onChange('note', e.target.value)}
          rows={2}
          disabled={isSubmitting}
        />
      </label>

      {errorMessage && (
        <p className="hmi-inline-error" role="alert">
          {errorMessage}
        </p>
      )}

      <div className="hmi-form-actions">
        <button
          type="button"
          className="hmi-secondary-button"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Back
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={handleStart}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Starting…' : 'Start Changeover'}
        </button>
      </div>
    </div>
  )
}
