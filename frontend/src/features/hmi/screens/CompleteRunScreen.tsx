import { OperatingContext } from '../../shared/OperatingContext'
import { completeRunFormErrors } from '../validation'
import type { CompleteRunFormValues, CompletionPreviewResponse, RunState } from '../types'

interface CompleteRunScreenProps {
  state: RunState
  values: CompleteRunFormValues
  preview: CompletionPreviewResponse | null
  isPreviewing: boolean
  isSubmitting: boolean
  errorMessage: string | null
  showErrors: boolean
  onChange: <K extends keyof CompleteRunFormValues>(
    field: K,
    value: CompleteRunFormValues[K],
  ) => void
  onCancel: () => void
  onReview: () => void
  onBackToEdit: () => void
  onConfirm: () => void
  /** Missed hours must be reported, one by one, before End Run. */
  onReportMissed?: () => void
}

export function CompleteRunScreen({
  state,
  values,
  preview,
  isPreviewing,
  isSubmitting,
  errorMessage,
  showErrors,
  onChange,
  onCancel,
  onReview,
  onBackToEdit,
  onConfirm,
  onReportMissed,
}: CompleteRunScreenProps) {
  const errors = completeRunFormErrors(values)
  const dueHours = (state.hours?.hours ?? []).filter((hour) => hour.status === 'due')
  const finalHour = state.hours?.current_hour ?? null
  const finalHourText = finalHour
    ? `${finalHour.hour_label.split('–')[0]} (the final part hour)`
    : 'the last reported hour'

  if (dueHours.length > 0 && !preview) {
    return (
      <div className="hmi-screen hmi-complete-run">
        <h1>End Run — {state.run.production_line}</h1>
        <p className="hmi-inline-warning" role="alert">
          Report {dueHours.length === 1 ? 'this hour' : `these ${dueHours.length} hours`} before ending
          the run: {dueHours.map((hour) => hour.hour_label).join(', ')}. Each hour is entered on its own.
        </p>
        <div className="hmi-form-actions">
          <button type="button" className="hmi-secondary-button" onClick={onCancel}>
            Back
          </button>
          {onReportMissed && (
            <button type="button" className="hmi-primary-button" onClick={onReportMissed}>
              Report Missed Hours
            </button>
          )}
        </div>
      </div>
    )
  }

  if (preview) {
    return (
      <div className="hmi-screen hmi-complete-run">
        <h1>End Run — review</h1>
        <p>These figures are calculated by Pulse from what has been recorded.</p>

        {preview.loss_review && <div role="status">
          <OperatingContext reports={preview.loss_review.operating_context} />
          <p>Remaining production gap: {preview.loss_review.remaining_gap_packs ?? 'Unknown standard'} packs
            ({preview.loss_review.equivalent_minutes ?? '—'} equivalent minutes). This is not measured downtime.</p>
          {preview.loss_review.prompt_required && <p>Please add what you know below. Cause unknown is allowed; the gap stays available for investigation.</p>}
          {preview.loss_review.limitations.map(message => <p key={message}>{message}</p>)}
          <label className="hmi-field">Reported explanation (optional; leave blank for cause unknown)
            <textarea value={values.lossReason ?? ''} onChange={e => onChange('lossReason', e.target.value)} />
          </label>
        </div>}
        <dl className="hmi-review-list">
          <div className="hmi-review-list__row">
            <dt>Total pallets recorded</dt>
            <dd>{preview.total_pallets_recorded}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Final part hour pallets</dt>
            <dd>{preview.final_pallets_produced}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Palletised packs</dt>
            <dd>{preview.palletised_packs}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>X-ray packs</dt>
            <dd>{preview.count_available ? preview.xray_pack_count : 'Count unavailable'}</dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Post-X-ray pack difference (estimated)</dt>
            <dd>
              {preview.post_xray_pack_difference === null ? '—' : preview.post_xray_pack_difference}
            </dd>
          </div>
          <div className="hmi-review-list__row">
            <dt>Post-X-ray waste (estimated)</dt>
            <dd>
              {preview.estimated_post_xray_waste_percent === null
                ? '—'
                : `${preview.estimated_post_xray_waste_percent}%`}
            </dd>
          </div>
        </dl>

        {/* The backend's method sentence already starts "Estimated from
            ...", so this label says how, rather than repeating it. The
            figures themselves stay labelled "(estimated)" above. */}
        <p className="hmi-field-help">How this is calculated: {preview.method}</p>

        {preview.data_quality_warning && (
          <p className="hmi-inline-error" role="alert">
            {preview.data_quality_warning}
          </p>
        )}

        {!preview.data_quality_warning && preview.waste_unavailable_reason && (
          <p className="hmi-inline-warning" role="status">
            {preview.waste_unavailable_reason}
          </p>
        )}

        {preview.can_complete ? (
          <p className="hmi-inline-warning" role="alert">
            This ends the run and stops its output clock. This cannot be undone from the HMI.
          </p>
        ) : (
          <p className="hmi-inline-error" role="alert">
            The run cannot be completed with these figures. Go back and correct the X-ray count
            or the final pallets, then review again.
          </p>
        )}

        {errorMessage && (
          <p className="hmi-inline-error" role="alert">
            {errorMessage}
          </p>
        )}

        <div className="hmi-form-actions">
          <button
            type="button"
            className="hmi-secondary-button"
            onClick={onBackToEdit}
            disabled={isSubmitting}
          >
            Back
          </button>
          <button
            type="button"
            className="hmi-primary-button"
            onClick={onConfirm}
            disabled={isSubmitting || !preview.can_complete}
          >
            {isSubmitting ? 'Ending…' : 'Confirm End Run'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="hmi-screen hmi-complete-run">
      <h1>End Run — {state.run.production_line}</h1>

      <fieldset className="hmi-field">
        <legend>Has any production been made since {finalHourText}?</legend>
        <label className="hmi-radio">
          <input
            type="radio"
            name="production-since-last-update"
            checked={values.productionSinceLastUpdate === 'yes'}
            onChange={() => onChange('productionSinceLastUpdate', 'yes')}
          />
          Yes
        </label>
        <label className="hmi-radio">
          <input
            type="radio"
            name="production-since-last-update"
            checked={values.productionSinceLastUpdate === 'no'}
            onChange={() => onChange('productionSinceLastUpdate', 'no')}
          />
          No
        </label>
        {showErrors && errors.productionSinceLastUpdate && (
          <span className="hmi-field-error" role="alert">
            {errors.productionSinceLastUpdate}
          </span>
        )}
      </fieldset>

      {values.productionSinceLastUpdate === 'yes' && (
        <label className="hmi-field">
          Pallets produced in the final part hour
          <input
            type="text"
            inputMode="decimal"
            value={values.finalPallets}
            onChange={(e) => onChange('finalPallets', e.target.value)}
            disabled={isSubmitting}
          />
          {showErrors && errors.finalPallets && (
            <span className="hmi-field-error" role="alert">
              {errors.finalPallets}
            </span>
          )}
        </label>
      )}

      <label className="hmi-field hmi-field--checkbox">
        <input
          type="checkbox"
          checked={values.countUnavailable}
          onChange={(e) => onChange('countUnavailable', e.target.checked)}
          disabled={isSubmitting}
        />
        Count unavailable
      </label>

      {values.countUnavailable ? (
        <label className="hmi-field">
          Why is the X-ray count unavailable?
          <textarea
            value={values.unavailableReason}
            onChange={(e) => onChange('unavailableReason', e.target.value)}
            rows={2}
            disabled={isSubmitting}
          />
          {showErrors && errors.unavailableReason && (
            <span className="hmi-field-error" role="alert">
              {errors.unavailableReason}
            </span>
          )}
        </label>
      ) : (
        <label className="hmi-field">
          X-ray pack count
          <input
            type="text"
            inputMode="numeric"
            value={values.xrayPackCount}
            onChange={(e) => onChange('xrayPackCount', e.target.value)}
            disabled={isSubmitting}
          />
          {showErrors && errors.xrayPackCount && (
            <span className="hmi-field-error" role="alert">
              {errors.xrayPackCount}
            </span>
          )}
        </label>
      )}

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
          disabled={isPreviewing}
        >
          Back
        </button>
        <button
          type="button"
          className="hmi-primary-button"
          onClick={onReview}
          disabled={isPreviewing}
        >
          {isPreviewing ? 'Checking…' : 'Review'}
        </button>
      </div>
    </div>
  )
}
