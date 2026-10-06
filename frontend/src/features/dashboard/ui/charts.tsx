import { barWidthPercent } from '../format'

/**
 * Chart colours are validated (dataviz validate_palette.js, dark mode,
 * surface #1c2224): target blue / actual green pass every check.
 * Downtime and loss bars are never distinguished by colour alone -
 * each sits in its own labelled row.
 */

export interface ChartSeries {
  key: string
  label: string
  /** CSS class suffix: pd-series--<tone>. */
  tone: 'target' | 'actual'
}

export interface ChartCategory {
  label: string
  /** null = no value (drawn as a gap, never as zero). */
  values: Record<string, number | null>
}

interface ColumnChartProps {
  /** Accessible name; also the caption of the data-table view. */
  label: string
  series: ChartSeries[]
  categories: ChartCategory[]
  format: (value: number | null) => string
}

/** Grouped vertical columns on one shared scale (never a second axis). */
export function ColumnChart({ label, series, categories, format }: ColumnChartProps) {
  const largest = Math.max(
    0,
    ...categories.flatMap((category) => series.map((s) => category.values[s.key] ?? 0)),
  )

  return (
    <figure className="pd-chart">
      <ul className="pd-legend" aria-hidden="true">
        {series.map((s) => (
          <li key={s.key}>
            <span className={`pd-legend__swatch pd-series--${s.tone}`} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="pd-columns" aria-hidden="true">
        {categories.map((category) => (
          <div
            key={category.label}
            className="pd-columns__group"
            data-tooltip={series.map((s) => `${s.label}: ${format(category.values[s.key])}`).join('\n')}
          >
            <div className="pd-columns__bars">
              {series.map((s) => {
                const value = category.values[s.key]
                return (
                  <span
                    key={s.key}
                    className={`pd-columns__bar pd-series--${s.tone}`}
                    style={{ height: `${value === null ? 0 : barWidthPercent(value, largest * 1.08)}%` }}
                  />
                )
              })}
            </div>
            <span className="pd-columns__label">{category.label}</span>
          </div>
        ))}
      </div>
      {/* The same figures as a table, for screen readers. */}
      <table className="pd-visually-hidden">
        <caption>{label}</caption>
        <thead>
          <tr>
            <th scope="col">Period</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category) => (
            <tr key={category.label}>
              <th scope="row">{category.label}</th>
              {series.map((s) => (
                <td key={s.key}>{format(category.values[s.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

export type BarTone = 'actual' | 'target' | 'planned' | 'unplanned' | 'other' | 'unexplained' | 'neutral'

export interface BarRow {
  label: string
  value: number | null
  display: string
  tone: BarTone
  /** Optional second line under the label. */
  note?: string
}

/** Labelled horizontal bars. `largest` fixes the scale (e.g. the measured
 * gap, or 100 for percentages) so rows are comparable. */
export function BarList({ rows, largest, label }: { rows: BarRow[]; largest: number; label: string }) {
  return (
    <ul className="pd-bars" aria-label={label}>
      {rows.map((row) => (
        <li key={row.label} className="pd-bars__row">
          <span className="pd-bars__label">
            {row.label}
            {row.note && <small>{row.note}</small>}
          </span>
          <span className="pd-bars__track" aria-hidden="true">
            <span
              className={`pd-bars__fill pd-series--${row.tone}`}
              style={{ width: `${barWidthPercent(row.value, largest)}%` }}
            />
          </span>
          <span className="pd-bars__value">{row.display}</span>
        </li>
      ))}
    </ul>
  )
}

interface TargetTrackProps {
  actual: number
  target: number
  /** Where actual should be by now at a linear weekly pace. */
  expectedByNow: number | null
  format: (value: number) => string
}

/** Actual progress against a target, with the pace marker. */
export function TargetTrack({ actual, target, expectedByNow, format }: TargetTrackProps) {
  const scale = Math.max(actual, target) * 1.1
  const position = (value: number) => `${barWidthPercent(value, scale)}%`

  return (
    <div className="pd-track">
      <div className="pd-track__bar" aria-hidden="true">
        <span className="pd-track__fill pd-series--actual" style={{ width: position(actual) }} />
        {expectedByNow !== null && (
          <span className="pd-track__marker pd-track__marker--pace" style={{ left: position(expectedByNow) }} />
        )}
        <span className="pd-track__marker pd-track__marker--target" style={{ left: position(target) }} />
      </div>
      <ul className="pd-track__legend">
        <li>
          <span className="pd-legend__swatch pd-series--actual" aria-hidden="true" /> Actual {format(actual)}
        </li>
        {expectedByNow !== null && (
          <li>
            <span className="pd-legend__line pd-legend__line--pace" aria-hidden="true" /> Needed by now{' '}
            {format(expectedByNow)}
          </li>
        )}
        <li>
          <span className="pd-legend__line" aria-hidden="true" /> Weekly target {format(target)}
        </li>
      </ul>
    </div>
  )
}
