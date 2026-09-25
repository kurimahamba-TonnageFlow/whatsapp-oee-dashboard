/**
 * Test-only builders for backend responses. Imported by the HMI test
 * files so each one describes a realistic RunState without repeating
 * the whole shape. Never imported by application code.
 */
import type {
  Changeover,
  HmiLineState,
  HmiLineStateResponse,
  PlannedDowntimeEvent,
  RunState,
} from './types'

/** A line with nothing running on it. */
export function availableLine(overrides: Partial<HmiLineState> = {}): HmiLineState {
  return {
    line_id: 1,
    production_line: 'Rovema',
    has_active_run: false,
    run_id: null,
    line_technician: null,
    shift: null,
    customer: null,
    product: null,
    started_at: null,
    planned_downtime_active: false,
    changeover_active: false,
    engineering_fault_open: false,
    open_fault_count: 0,
    last_activity_at: null,
    stale_status: 'no_active_run',
    stale_reason: 'No active production run.',
    minutes_since_last_hourly_update: null,
    ...overrides,
  }
}

/** A line already running - on this device or on another one. */
export function activeLine(overrides: Partial<HmiLineState> = {}): HmiLineState {
  return {
    ...availableLine(),
    has_active_run: true,
    run_id: 99,
    line_technician: 'Liam',
    shift: 'Days',
    customer: 'Asda',
    product: 'White Basmati',
    started_at: '2026-01-12T06:05:00+00:00',
    last_activity_at: '2026-01-12T07:05:00+00:00',
    stale_status: 'current',
    stale_reason: null,
    minutes_since_last_hourly_update: 25,
    ...overrides,
  }
}

export function lineStateResponse(lines: HmiLineState[]): HmiLineStateResponse {
  return {
    generated_at: '2026-01-12T08:00:00+00:00',
    stale_after_minutes: 75,
    lines,
  }
}

/** Rovema, GIC and Guill all free - the common starting point. */
export function allLinesAvailable(): HmiLineStateResponse {
  return lineStateResponse([
    availableLine({ line_id: 1, production_line: 'Rovema' }),
    availableLine({ line_id: 2, production_line: 'GIC' }),
    availableLine({ line_id: 3, production_line: 'Guill' }),
  ])
}

export function plannedDowntimeEvent(
  overrides: Partial<PlannedDowntimeEvent> = {},
): PlannedDowntimeEvent {
  return {
    planned_downtime_id: 31,
    production_run_id: 99,
    production_line: 'Rovema',
    reason: 'Label Change',
    started_by: 'Liam',
    started_at: '2026-01-12T07:30:00+00:00',
    ended_by: null,
    ended_at: null,
    duration_minutes: null,
    is_active: true,
    elapsed_minutes: 11,
    ...overrides,
  }
}

export function changeover(overrides: Partial<Changeover> = {}): Changeover {
  return {
    changeover_id: 6,
    production_line: 'Rovema',
    line_technician: 'Liam',
    shift: 'Day',
    status: 'Open',
    started_at: '2026-01-12T07:30:00+00:00',
    completed_at: null,
    completed_by: null,
    duration_minutes: null,
    previous_customer: 'Asda',
    previous_product: 'White Basmati',
    previous_pack_weight_kg: 1,
    previous_format: 'Pillow',
    new_production_run_id: null,
    new_customer: 'Tesco',
    new_product: 'Jasmine',
    new_pack_weight_kg: 4,
    new_format: 'Block bottom',
    note: null,
    ...overrides,
  }
}

export function runState(overrides: Partial<RunState> = {}): RunState {
  return {
    // Overridable: screens add the time elapsed since generated_at to
    // any active duration, so a test controlling that needs to control
    // this too.
    generated_at: overrides.generated_at ?? '2026-01-12T08:00:00+00:00',
    run: {
      run_id: 99,
      production_line: 'Rovema',
      line_technician: 'Liam',
      shift: 'Days',
      customer: 'Asda',
      product: 'White Basmati',
      format: 'Pillow',
      pack_type: '1 kg x 8',
      pack_weight_kg: 1,
      packs_per_case: 8,
      cases_per_pallet: 220,
      target_speed_ppm: 120,
      status: 'Active',
      started_at: '2026-01-12T06:05:00+00:00',
      finished_at: null,
      starting_pallets_remaining: 38,
      pallets_remaining: 34.25,
      total_pallets_completed: 3.75,
      potential_overrun_pallets: 0,
      ...overrides.run,
    },
    progress: {
      hourly_update_count: 1,
      pallets_recorded: 3.75,
      expected_packs: 7200,
      actual_packs: 6600,
      output_gap_packs: 600,
      expected_tonnes: 7.2,
      actual_tonnes: 6.6,
      production_achievement_percent: 91.7,
      planned_downtime_minutes: 0,
      planned_downtime_completed_minutes: 0,
      planned_downtime_active_minutes: null,
      changeover_active_minutes: null,
      unplanned_downtime_minutes: 0,
      open_faults: 0,
      last_period_ended_at: '2026-01-12T07:05:00+00:00',
      next_hourly_update_due_at: '2026-01-12T08:10:00+00:00',
      ...overrides.progress,
    },
    open_planned_downtime: overrides.open_planned_downtime ?? null,
    open_changeover: overrides.open_changeover ?? null,
  }
}

export const HMI_CONFIG = {
  lines: [
    {
      id: 1,
      name: 'Rovema',
      machines: [
        {
          id: 10,
          name: 'BV1',
          buttons: [
            {
              id: 20,
              name: 'Film Jam',
              event_type: 'unplanned_fault' as const,
              ownership: 'Production' as const,
              fault_category: null,
            },
          ],
        },
        { id: 11, name: 'Casepacker', buttons: [] },
      ],
    },
  ],
}
