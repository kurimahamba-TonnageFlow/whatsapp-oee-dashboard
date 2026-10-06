import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiRequestError, apiClient } from '../../api/client'
import { useEngineeringWrites } from './recovery'
import { RecoveryPanel } from './RecoveryPanel'
import { RepairUpdateForm } from './RepairUpdateForm'
import { HandoverForm } from './HandoverForm'

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())
function Harness({ actor = 'Alfie', send, expired = vi.fn(), scope = 'fault' as 'fault' | 'casepacker' }: { actor?: string; send: (key: string) => Promise<unknown>; expired?: () => void; scope?: 'fault' | 'casepacker' }) {
  const writes = useEngineeringWrites(actor, 'token')
  return <>
    <button onClick={() => { void writes.perform(scope, 7, 'update', { note: 'Original report' }, send).catch(() => {}) }}>Submit</button>
    <RecoveryPanel actor={actor} token="token" scope={scope} onSaved={vi.fn()} onSessionExpired={expired} />
  </>
}
it.each(['fault','casepacker'] as const)('recovers %s after remount and replays original payload/key', async scope => {
  const send = vi.fn().mockRejectedValue(new ApiRequestError(0, 'Lost reply'))
  const page = render(<Harness send={send} scope={scope} />)
  fireEvent.click(screen.getByText('Submit'))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  const key = send.mock.calls[0][0]
  page.unmount()
  const replay = vi.spyOn(apiClient, 'post').mockResolvedValue({})
  render(<Harness send={send} scope={scope} />)
  fireEvent.click(screen.getByText('Retry original update'))
  await waitFor(() => expect(replay).toHaveBeenCalledWith(expect.any(String), { note: 'Original report' }, { token: 'token', idempotencyKey: key }))
  await waitFor(() => expect(screen.queryByText('Retry original update')).not.toBeInTheDocument())
})
it('blocks a second submission while the original action is uncertain', async () => {
  const send = vi.fn().mockRejectedValue(new ApiRequestError(503, 'Uncertain'))
  render(<Harness send={send} />)
  fireEvent.click(screen.getByText('Submit'))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByText('Submit'))
  expect(send).toHaveBeenCalledTimes(1)
})
it('retains pending work on session expiry and does not show it to another engineer', async () => {
  const send = vi.fn().mockRejectedValue(new ApiRequestError(401, 'Expired'))
  const page = render(<Harness send={send} />)
  fireEvent.click(screen.getByText('Submit'))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  page.unmount()
  const other = render(<Harness actor="Aaron" send={send} />)
  expect(screen.queryByText('Retry original update')).not.toBeInTheDocument()
  other.unmount()
  render(<Harness send={send} />)
  expect(screen.getByText('Retry original update')).toBeInTheDocument()
})
it('clears a definitive conflict but retains an uncertain error', async () => {
  const send = vi.fn().mockRejectedValue(new ApiRequestError(409, 'Handed over'))
  render(<Harness send={send} />)
  fireEvent.click(screen.getByText('Submit'))
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.queryByText('Retry original update')).not.toBeInTheDocument())
})
it('does not send a new action if durable storage is blocked', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked') })
  const send = vi.fn()
  render(<Harness send={send} />)
  await act(async () => { fireEvent.click(screen.getByText('Submit')) })
  expect(send).not.toHaveBeenCalled()
})
it('keeps the repair draft across remount and clears only after confirmed save signal', () => {
  const page = render(<RepairUpdateForm draftKey="fault:Alfie:7:update" mode="update" isSubmitting={false} onSubmit={vi.fn()} resetSignal={0} />)
  fireEvent.change(screen.getByLabelText(/Finding/), { target: { value: 'Guide worn' } })
  page.unmount()
  const next = render(<RepairUpdateForm draftKey="fault:Alfie:7:update" mode="update" isSubmitting={false} onSubmit={vi.fn()} resetSignal={0} />)
  expect(screen.getByLabelText(/Finding/)).toHaveValue('Guide worn')
  next.rerender(<RepairUpdateForm draftKey="fault:Alfie:7:update" mode="update" isSubmitting={false} onSubmit={vi.fn()} resetSignal={1} />)
  expect(screen.getByLabelText(/Finding/)).toHaveValue('')
})
it('keeps handover notes across closing and reopening the form', () => {
  const page = render(<HandoverForm draftKey="fault:Alfie:7:handover" isSubmitting={false} onSubmit={vi.fn()} />)
  fireEvent.change(screen.getByLabelText(/Handover note/), { target: { value: 'Check the program next shift' } })
  page.unmount()
  render(<HandoverForm draftKey="fault:Alfie:7:handover" isSubmitting={false} onSubmit={vi.fn()} />)
  expect(screen.getByLabelText(/Handover note/)).toHaveValue('Check the program next shift')
})
