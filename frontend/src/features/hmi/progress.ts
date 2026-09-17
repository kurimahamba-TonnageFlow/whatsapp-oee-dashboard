import type { ActiveRunRecord } from './types'

export interface RunProgress {
  totalPalletsCompleted: number
  palletsRemaining: number
  percentComplete: number
  elapsedMinutes: number
  expectedPacks: number
  actualPacks: number
  outputGapPacks: number
}

/** Derives live progress figures from the run's starting configuration
 * plus what's been recorded since (hourly-update totals - currently
 * fixture-backed, see awaitingApiIntegration.ts). Expected output uses
 * the same target_speed_ppm-based formula documented in
 * docs/dashboard_integration.md, applied to elapsed real time. */
export function deriveRunProgress(run: ActiveRunRecord, now: Date = new Date()): RunProgress {
  const initialPalletsRemaining = Number(run.form.palletsRemaining) || 0
  const casesPerPallet = Number(run.form.casesPerPallet) || 0
  const packsPerCase = Number(run.form.packsPerCase) || 0
  const targetSpeedPpm = Number(run.form.targetSpeedPpm) || 0

  const palletsRemaining = Math.max(initialPalletsRemaining - run.totalPalletsCompleted, 0)
  const totalPlanned = run.totalPalletsCompleted + palletsRemaining
  const percentComplete = totalPlanned > 0 ? (run.totalPalletsCompleted / totalPlanned) * 100 : 0

  const elapsedMinutes = Math.max(
    (now.getTime() - new Date(run.startedAtIso).getTime()) / 60000,
    0,
  )

  const expectedPacks = targetSpeedPpm * elapsedMinutes
  const actualPacks = run.totalPalletsCompleted * casesPerPallet * packsPerCase

  return {
    totalPalletsCompleted: run.totalPalletsCompleted,
    palletsRemaining,
    percentComplete,
    elapsedMinutes,
    expectedPacks,
    actualPacks,
    outputGapPacks: Math.max(expectedPacks - actualPacks, 0),
  }
}

export function formatDuration(totalMinutes: number): string {
  const minutes = Math.max(Math.floor(totalMinutes), 0)
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `${hours}h ${remainder}m`
}

/** Simple, documented default thresholds - adjustable later, not a
 * claim of precise business rules. */
export function statusToneForProgress(
  percentComplete: number,
  outputGapPacks: number,
): 'green' | 'amber' | 'red' {
  if (outputGapPacks === 0) return 'green'
  if (percentComplete >= 50) return 'amber'
  return 'red'
}
