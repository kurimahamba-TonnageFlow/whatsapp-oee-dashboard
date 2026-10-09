import type { LiveLine, LiveSnapshot, LiveWindow } from '../liveTypes'
import type { LineStops } from '../types'
export interface LossDriver {
  line: string; machine: string; cause: string; minutes: number; events: number
  fault_ids: number[]; estimated_tonnes: number | null; investigation: string
}
export interface IntelligenceSnapshot {
  generated_at: string; window: LiveWindow; configured_lines: string[]; selected_line: string | null
  weekly: LiveSnapshot['weekly'] & { elapsed_percent: number; elapsed_days: number; comparison_percent: number | null; comparison_note: string }
  lines: (Omit<LiveLine, 'trend'> & { current_issue: string; current_fault_id: number | null })[]
  output_gap: { total_tonnes: number | null; unclassified_tonnes: number | null; recoverable_tonnes: number | null; delayed_tonnes: number | null; confirmed_unrecovered_tonnes: number | null; note: string }
  downtime: { planned_minutes: number; unplanned_minutes: number; not_scheduled_minutes: number; unplanned_percent: number | null }
  loss_drivers: LossDriver[]; ranking_method: string; line_stops: LineStops
  material_flow: { stage: string; connected: boolean; tonnes: number | null }[]
  data_issues: string[]; capabilities: { production_intelligence: boolean; financial_intelligence: boolean; scope: string }
}
