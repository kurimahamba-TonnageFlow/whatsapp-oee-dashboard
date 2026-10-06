import { formatShortDate, formatTonnes, localDatePart } from './format'
import type { WeeklyTargetsResponse } from './types'
import { ColumnChart } from './ui/charts'
import { EmptyState, Notice } from './ui/states'
import { weekProgress } from './weekly'

/** Weekly target against actual tonnes, one pair of columns per production week. */
export function WeeklyTonnageChart({ weeks, line }: { weeks: WeeklyTargetsResponse[]; line: string }) {
  if (weeks.length === 0) {
    return <EmptyState>No weekly figures were returned.</EmptyState>
  }

  const excluded = weeks.find((week) => week.data_quality.legacy_records_excluded)
  const anyTarget = weeks.some((week) => weekProgress(week, line)?.target_tonnes != null)
  const anyActual = weeks.some((week) => (weekProgress(week, line)?.actual_tonnes ?? 0) > 0)

  if (!anyTarget && !anyActual) {
    return (
      <>
        <EmptyState title="Nothing to chart yet">
          No timestamped production and no weekly target have been recorded
          {line ? ` for ${line}` : ''} in the last {weeks.length} production weeks.
        </EmptyState>
        {excluded?.data_quality.message && <Notice>{excluded.data_quality.message}</Notice>}
      </>
    )
  }

  return (
    <>
      <ColumnChart
        label={`Weekly tonnes against target${line ? ` - ${line}` : ''}`}
        series={[
          { key: 'target', label: 'Weekly target', tone: 'target' },
          { key: 'actual', label: 'Actual tonnes', tone: 'actual' },
        ]}
        categories={weeks.map((week, index) => {
          const progress = weekProgress(week, line)
          return {
            label:
              index === weeks.length - 1
                ? 'This week'
                : formatShortDate(localDatePart(week.week.start_local)),
            values: {
              target: progress?.target_tonnes ?? null,
              actual: progress?.actual_tonnes ?? null,
            },
          }
        })}
        format={(value) => (value === null ? 'Not set' : formatTonnes(value))}
      />
      <p className="pd-panel__note">
        Production weeks run Monday 06:00 to Monday 06:00 (UK time), labelled by their Monday.
        {!anyTarget && ' No weekly target has been set for these weeks, so only actual tonnes are shown.'}
      </p>
      {excluded?.data_quality.message && <Notice>{excluded.data_quality.message}</Notice>}
    </>
  )
}
