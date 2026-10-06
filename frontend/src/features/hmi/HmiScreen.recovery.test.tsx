import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as api from './api'
import { saveActiveRun } from './activeRunStorage'
import { HMI_CONFIG, allLinesAvailable, runState } from './hmiTestState'
import { ApiRequestError } from '../../api/client'
vi.mock('./api')
const key = 'k-recovery-test-000000000001'
const cases = [
  { kind: 'targetSpeed', api: 'changeTargetSpeed', payload: { newSpeed: '95', reason: 'Film trial', semantics: 'operating' }, id: 99, body: { line_technician: 'Liam', new_operating_speed_ppm: '95', reason: 'Film trial', effective_at: undefined, supersedes_id: undefined } },
  { kind: 'plannedDowntimeStart', api: 'startPlannedDowntime', payload: { reason: 'Film Change' }, id: 99, body: { reason: 'Film Change', started_by: 'Liam' } },
  { kind: 'plannedDowntimeEnd', api: 'endPlannedDowntime', payload: { id: 31 }, id: 31, body: { ended_by: 'Liam' } },
  { kind: 'changeoverStart', api: 'startChangeover', payload: { line_technician: 'Liam', new_customer: 'Asda', new_product: 'Basmati', new_pack_weight_kg: '1', new_format: 'Pillow', note: 'Saved detail' }, id: 99, body: { line_technician: 'Liam', new_customer: 'Asda', new_product: 'Basmati', new_pack_weight_kg: '1', new_format: 'Pillow', note: 'Saved detail' } },
  { kind: 'changeoverComplete', api: 'completeChangeover', payload: { id: 71 }, id: 71, body: { completed_by: 'Liam', first_acceptable_packs_confirmed: true } },
  { kind: 'completeRun', api: 'completeRun', payload: { line_technician: 'Liam', production_since_last_update: true, final_pallets_produced: '1.25', count_unavailable: false, xray_pack_count: 2000 }, id: 99, body: { line_technician: 'Liam', production_since_last_update: true, final_pallets_produced: '1.25', count_unavailable: false, xray_pack_count: 2000 } },
] as const
beforeEach(() => {
  vi.mocked(api.getHmiConfig).mockResolvedValue(HMI_CONFIG)
  vi.mocked(api.getLineState).mockResolvedValue(allLinesAvailable())
  vi.mocked(api.getRunState).mockResolvedValue(runState())
})
afterEach(() => {
  for (const c of cases) vi.mocked(api[c.api]).mockReset()
  vi.mocked(api.getHmiConfig).mockReset(); vi.mocked(api.getLineState).mockReset(); vi.mocked(api.getRunState).mockReset()
  localStorage.clear()
})
async function restore(c: typeof cases[number]) {
  saveActiveRun({ runId: 99, productionLine: 'Rovema' })
  localStorage.setItem('pulse.hmi.pendingAction.v1', JSON.stringify({ kind: c.kind, key, runId: 99, label: 'Saved action', payload: c.payload, createdAtIso: '2026-01-12T08:00:00Z' }))
  render(<MemoryRouter><HmiScreen /></MemoryRouter>)
  await screen.findByRole('button', { name: 'Check and retry' })
}
it.each(cases)('replays saved $kind after reload without re-entering details', async c => {
  vi.mocked(api[c.api]).mockResolvedValue({} as never)
  await restore(c)
  expect(api[c.api]).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check and retry' }))
  await waitFor(() => expect(api[c.api]).toHaveBeenCalledWith(c.id, c.body, key))
  await waitFor(() => expect(localStorage.getItem('pulse.hmi.pendingAction.v1')).toBeNull())
  if (c.kind === 'completeRun') await screen.findByRole('heading', { name: 'What happens next on Rovema?' })
})
it('keeps the saved target change after another lost reply and reuses it when the connection returns', async () => {
  const c = cases[0]
  vi.mocked(api.changeTargetSpeed).mockRejectedValueOnce(new ApiRequestError(0, 'Lost reply')).mockResolvedValue({} as never)
  await restore(c)
  fireEvent.click(screen.getByRole('button', { name: 'Check and retry' }))
  await screen.findByText(/may already have saved/)
  expect(JSON.parse(localStorage.getItem('pulse.hmi.pendingAction.v1')!).key).toBe(key)
  fireEvent.click(screen.getByRole('button', { name: 'Check and retry' }))
  await waitFor(() => expect(api.changeTargetSpeed).toHaveBeenCalledTimes(2))
  expect(vi.mocked(api.changeTargetSpeed).mock.calls[1]).toEqual(vi.mocked(api.changeTargetSpeed).mock.calls[0])
})
