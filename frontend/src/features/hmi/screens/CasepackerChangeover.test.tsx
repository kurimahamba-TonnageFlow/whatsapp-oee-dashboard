import { fireEvent, render, screen, waitFor, act } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { EndRunNextScreen } from './EndRunNextScreen'
import { LineStoppageScreen } from './LineStoppageScreen'
import { getCasepackerStatus, type CasepackerRequest } from '../../engineering/casepackerApi'
vi.mock('../../engineering/casepackerApi')
const request: CasepackerRequest = { id: 1, line_stoppage_id: 11, production_line: 'Rovema', details: '1kg x8 Sainsbury program', requested_by: 'Liam', requested_at: '2026-10-03T00:00:00Z', engineer: null, accepted_at: null, ready_at: null, updates: [] }
beforeEach(() => { vi.mocked(getCasepackerStatus).mockReset() })
afterEach(() => vi.useRealTimers())
it('requires an explicit format-change choice and details for Engineering', () => {
  const onChangeover = vi.fn()
  render(<EndRunNextScreen productionLine="Rovema" technician="Liam" isSubmitting={false} errorMessage={null} onEndShift={vi.fn()} onChangeover={onChangeover} onOther={vi.fn()} onNotScheduled={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: /Changeover/ }))
  const start = screen.getByRole('button', { name: 'Start Changeover' })
  expect(start).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: /Yes - call Engineering/ }))
  expect(start).toBeDisabled()
  fireEvent.change(screen.getByLabelText(/Required casepacker format/), { target: { value: '  1kg x8 Sainsbury program  ' } })
  fireEvent.click(start)
  expect(onChangeover).toHaveBeenCalledWith(true, '1kg x8 Sainsbury program')
})
function timer() {
  return render(<LineStoppageScreen stoppage={{ stoppageId: 11, productionLine: 'Rovema', kind: 'changeover', reason: null, startedAt: '2026-10-03T00:00:00Z', startedBy: 'Liam', physicalEndedAt: '2026-10-03T00:10:00Z', endedAt: null, durationMinutes: null }} isSubmitting={false} errorMessage={null} onEnd={vi.fn()} onStartNewRun={vi.fn()} onHome={vi.fn()} />)
}
it('keeps the next run blocked after physical changeover until Engineering readiness arrives', async () => {
  vi.mocked(getCasepackerStatus).mockResolvedValue({ request })
  timer()
  const start = screen.getByRole('button', { name: 'Enter New Run Details' })
  expect(start).toBeDisabled()
  await screen.findByText(/Waiting for Engineering - next run blocked/)
  expect(start).toBeDisabled()

})
it('reload reads ready status and allows the next run', async () => {
  vi.mocked(getCasepackerStatus).mockResolvedValue({ request: { ...request, engineer: 'Alfie', ready_at: '2026-10-03T00:20:00Z' } })
  timer()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Enter New Run Details' })).toBeEnabled())
  expect(screen.getByText('Casepacker ready')).toBeInTheDocument()
})
it('a failed readiness check cannot release the next run', async () => {
  vi.mocked(getCasepackerStatus).mockRejectedValue(new Error('offline'))
  timer()
  await screen.findByText(/Could not check casepacker readiness/)
  expect(screen.getByRole('button', { name: 'Enter New Run Details' })).toBeDisabled()
})
it('polls readiness and releases the gate when Engineering finishes', async () => {
  vi.useFakeTimers()
  vi.mocked(getCasepackerStatus).mockResolvedValue({ request })
  timer()
  await act(async () => { await Promise.resolve() })
  expect(screen.getByRole('button', { name: 'Enter New Run Details' })).toBeDisabled()
  vi.mocked(getCasepackerStatus).mockResolvedValue({ request: { ...request, engineer: 'Alfie', ready_at: '2026-10-03T00:20:00Z' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(screen.getByRole('button', { name: 'Enter New Run Details' })).toBeEnabled()
})
