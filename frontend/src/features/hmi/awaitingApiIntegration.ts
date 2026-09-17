/**
 * ============================================================
 * AWAITING API INTEGRATION - every function below is a controlled,
 * local fixture. Nothing here calls a real backend endpoint, and
 * nothing here ever reaches Supabase.
 * ============================================================
 *
 * Confirmed live endpoints for this stage are only:
 *   GET /health, GET /api/v1/hmi/config, POST /api/v1/runs,
 *   POST /api/v1/runs/{run_id}/complete
 * (see docs/hmi_integration.md). No backend endpoint exists yet for
 * hourly updates, starting/ending planned downtime, or reporting a
 * fault to Engineering - see frontend/HMI_FRONTEND_STATUS.md.
 *
 * These functions exist so the visual workflow can be built and
 * tested now, with an obvious seam to swap in a real apiClient call
 * later without changing any call site. IDs returned here are always
 * prefixed "local-fixture-" so they are unmistakable in logs/state.
 */

import type { StartRunFormValues } from './types'

const FIXTURE_NETWORK_DELAY_MS = 350

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), FIXTURE_NETWORK_DELAY_MS)
  })
}

function fixtureId(prefix: string): string {
  return `local-fixture-${prefix}-${Date.now()}`
}

// ------------------------------------------------------------
// Hourly update
// ------------------------------------------------------------

export interface HourlyUpdateInput {
  palletsProducedThisPeriod: number
}

export interface HourlyUpdateResult {
  previousTotal: number
  newTotal: number
  palletsProducedThisPeriod: number
  palletsRemaining: number
  expectedPacksThisPeriod: number
  actualPacksThisPeriod: number
  outputGapPacks: number
}

/** AWAITING API INTEGRATION - fixture only. Uses the same
 * expected-output formula documented in docs/dashboard_integration.md
 * (target_speed_ppm * 60 minutes) applied to a single hourly period. */
export async function submitHourlyUpdate(
  run: StartRunFormValues,
  totalPalletsCompletedSoFar: number,
  input: HourlyUpdateInput,
): Promise<HourlyUpdateResult> {
  const targetSpeedPpm = Number(run.targetSpeedPpm) || 0
  const casesPerPallet = Number(run.casesPerPallet) || 0
  const packsPerCase = Number(run.packsPerCase) || 0
  const palletsRemaining = Number(run.palletsRemaining) || 0

  const previousTotal = totalPalletsCompletedSoFar
  const newTotal = previousTotal + input.palletsProducedThisPeriod

  const expectedPacksThisPeriod = targetSpeedPpm * 60
  const actualPacksThisPeriod = input.palletsProducedThisPeriod * casesPerPallet * packsPerCase

  return delay({
    previousTotal,
    newTotal,
    palletsProducedThisPeriod: input.palletsProducedThisPeriod,
    palletsRemaining: Math.max(palletsRemaining - input.palletsProducedThisPeriod, 0),
    expectedPacksThisPeriod,
    actualPacksThisPeriod,
    outputGapPacks: Math.max(expectedPacksThisPeriod - actualPacksThisPeriod, 0),
  })
}

// ------------------------------------------------------------
// Planned downtime
// ------------------------------------------------------------

export interface PlannedDowntimeEvent {
  id: string
  reason: string
  startedAtIso: string
}

/** AWAITING API INTEGRATION - fixture only (local state, not
 * persisted server-side). */
export async function startPlannedDowntime(reason: string): Promise<PlannedDowntimeEvent> {
  return delay({ id: fixtureId('downtime'), reason, startedAtIso: new Date().toISOString() })
}

export interface PlannedDowntimeEndResult {
  endedAtIso: string
  minutes: number
}

/** AWAITING API INTEGRATION - fixture only. */
export async function endPlannedDowntime(startedAtIso: string): Promise<PlannedDowntimeEndResult> {
  const endedAtIso = new Date().toISOString()
  const minutes = Math.max(
    Math.round((new Date(endedAtIso).getTime() - new Date(startedAtIso).getTime()) / 60000),
    0,
  )
  return delay({ endedAtIso, minutes })
}

// ------------------------------------------------------------
// Report to Engineer
// ------------------------------------------------------------

export interface EngineerReportInput {
  productionLine: string
  machine: string
  faultReason: string
  note?: string
}

export interface EngineerReportResult {
  reference: string
  reportedAtIso: string
}

/** AWAITING API INTEGRATION - fixture only. */
export async function reportFaultToEngineer(
  input: EngineerReportInput,
): Promise<EngineerReportResult> {
  void input
  return delay({ reference: fixtureId('fault'), reportedAtIso: new Date().toISOString() })
}
