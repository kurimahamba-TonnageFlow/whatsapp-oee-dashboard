import { beforeEach as resetEngineeringStorage } from 'vitest'
resetEngineeringStorage(() => localStorage.clear())
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CasepackerQueue } from './CasepackerQueue'
import { actOnCasepacker, getCasepackerRequests, type CasepackerRequest } from './casepackerApi'
import { apiClient, ApiRequestError } from '../../api/client'
vi.mock('./casepackerApi')
const job: CasepackerRequest = { id: 7, line_stoppage_id: 11, production_line: 'Rovema', details: '1kg x8 Sainsbury program', requested_by: 'Liam', requested_at: '2026-10-03T00:00:00Z', engineer: null, accepted_at: null, ready_at: null, updates: [] }
beforeEach(() => { vi.mocked(actOnCasepacker).mockReset(); vi.mocked(getCasepackerRequests).mockReset() })
function show(item = job) {
  vi.mocked(getCasepackerRequests).mockResolvedValue({ items: [item] })
  render(<CasepackerQueue token="token" engineerName="Alfie" onSessionExpired={vi.fn()} />)
}
it('accepts a changeover request and displays its required format', async () => {
  vi.mocked(actOnCasepacker).mockResolvedValue({})
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Accept changeover' }))
  await waitFor(() => expect(actOnCasepacker).toHaveBeenCalledWith('token', 7, 'accept', '', expect.any(String)))
  expect(screen.getByText(job.details)).toBeInTheDocument()
})
it('requires work details and explicit readiness confirmation', async () => {
  vi.mocked(actOnCasepacker).mockResolvedValue({})
  show({ ...job, engineer: 'Alfie' })
  const ready = await screen.findByRole('button', { name: 'Casepacker ready' })
  expect(ready).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Casepacker work details'), { target: { value: 'Program and guides verified' } })
  fireEvent.click(ready)
  expect(actOnCasepacker).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm casepacker ready' }))
  await waitFor(() => expect(actOnCasepacker).toHaveBeenCalledWith('token', 7, 'ready', 'Program and guides verified', expect.any(String)))
})
it('retries an uncertain save with the same idempotency key', async () => {
  vi.mocked(actOnCasepacker).mockRejectedValueOnce(new ApiRequestError(0, 'Connection lost')).mockResolvedValue({})
  show({ ...job, engineer: 'Alfie' })
  const field = await screen.findByLabelText('Casepacker work details')
  fireEvent.change(field, { target: { value: 'Guides adjusted' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add changeover update' }))
  await screen.findByText('Connection lost')
  const first = vi.mocked(actOnCasepacker).mock.calls[0]
  const replay = vi.spyOn(apiClient, 'post').mockResolvedValue({})
  fireEvent.click(screen.getByRole('button', { name: 'Retry original update' }))
  await waitFor(() => expect(replay).toHaveBeenCalledWith('/api/v1/engineering/casepacker-requests/7/actions', { action: 'update', note: first[3] }, { token: 'token', idempotencyKey: first[4] }))
  replay.mockRestore()
})
it('does not offer readiness controls to a different engineer', async () => {
  show({ ...job, engineer: 'Aaron' })
  await screen.findByText('Accepted by Aaron')
  expect(screen.queryByRole('button', { name: 'Casepacker ready' })).not.toBeInTheDocument()
})

it('requires a note and confirmation before handing over a changeover', async () => {
  vi.mocked(actOnCasepacker).mockResolvedValue({})
  show({ ...job, engineer: 'Alfie' })
  const handover = await screen.findByRole('button', { name: 'Hand over changeover' })
  expect(handover).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Casepacker work details'), { target: { value: 'Guides set. Program still needs checking.' } })
  fireEvent.click(handover)
  expect(actOnCasepacker).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm changeover handover' }))
  await waitFor(() => expect(actOnCasepacker).toHaveBeenCalledWith('token', 7, 'handover', 'Guides set. Program still needs checking.', expect.any(String)))
})

it('ignores an older casepacker response after a newer refresh', async () => {
  let oldResponse!: (value: { items: CasepackerRequest[] }) => void
  vi.mocked(getCasepackerRequests).mockReturnValueOnce(new Promise(resolve => { oldResponse = resolve }))
    .mockResolvedValueOnce({ items: [{ ...job, details: 'Newest format', ready_at: '2026-10-04T10:00:00Z' }] })
  render(<CasepackerQueue token="token" engineerName="Alfie" onSessionExpired={vi.fn()} />)
  fireEvent.click(screen.getByText('Refresh changeovers'))
  await screen.findByText('Newest format')
  await act(async () => { oldResponse({ items: [job] }) })
  expect(screen.getByText('Newest format')).toBeInTheDocument()
  expect(screen.queryByText(job.details)).not.toBeInTheDocument()
})

it('keeps recovery visible when polling replaces ready controls', async () => {
  vi.mocked(actOnCasepacker).mockRejectedValueOnce(new ApiRequestError(0, 'Reply lost'))
  show({ ...job, engineer: 'Alfie' })
  fireEvent.change(await screen.findByLabelText('Casepacker work details'), { target: { value: 'Program verified' } })
  fireEvent.click(screen.getByRole('button', { name: 'Casepacker ready' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm casepacker ready' }))
  await screen.findByText('Reply lost')
  vi.mocked(getCasepackerRequests).mockResolvedValue({ items: [] })
  fireEvent.click(screen.getByText('Refresh changeovers'))
  await screen.findByText('No casepacker requests waiting for the next run.')
  expect(screen.getByText('Retry original ready')).toBeInTheDocument()
})
