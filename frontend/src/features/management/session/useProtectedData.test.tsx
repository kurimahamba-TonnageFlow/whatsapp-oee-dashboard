import { act, cleanup, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError } from '../../../api/client'
import * as managementApi from '../api'
import { ManagementSessionProvider } from './ManagementSessionProvider'
import { REQUEST_TIMEOUT_MS, useProtectedData, type ProtectedData } from './useProtectedData'
import { useManagementSession } from './useManagementSession'

vi.mock('../api')

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.mocked(managementApi.logout).mockReset()
})

type Loader = (token: string, signal: AbortSignal) => Promise<string>

let latest!: ProtectedData<string>

function Harness({ load, dataKey }: { load: Loader; dataKey: string }) {
  const { session, signIn, notice } = useManagementSession()
  useEffect(() => {
    signIn({ status: 'success', token: 'hook-token', manager_name: 'Kuri', expires_at: '2099-01-01T00:00:00+00:00' })
  }, [signIn])
  latest = useProtectedData(load, dataKey)
  return (
    <p>
      {session ? 'signed in' : 'signed out'} | {latest.isLoading ? 'loading' : 'idle'} | {latest.data ?? ''} |{' '}
      {latest.error ?? ''} | {notice ?? ''}
    </p>
  )
}

function renderHarness(load: Loader, dataKey = 'a') {
  vi.mocked(managementApi.logout).mockResolvedValue({ status: 'success', message: 'Logged out.' })
  const utils = render(
    <ManagementSessionProvider>
      <Harness load={load} dataKey={dataKey} />
    </ManagementSessionProvider>,
  )
  return {
    ...utils,
    rerenderWith: (nextLoad: Loader, nextKey: string) =>
      utils.rerender(
        <ManagementSessionProvider>
          <Harness load={nextLoad} dataKey={nextKey} />
        </ManagementSessionProvider>,
      ),
  }
}

/** Never answers; rejects only when its request is abandoned. */
function stalled(): Loader {
  return (_token, signal) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new ApiRequestError(0, 'aborted')))
    })
}

describe('useProtectedData', () => {
  it('loads with the shared session token', async () => {
    const load = vi.fn<Loader>().mockResolvedValue('figures')
    renderHarness(load)

    expect(await screen.findByText(/figures/)).toBeInTheDocument()
    expect(load).toHaveBeenCalledWith('hook-token', expect.any(AbortSignal))
    expect(latest.loadedAt).toBeInstanceOf(Date)
  })

  it('abandons a request after the timeout with a clear message, instead of loading forever', async () => {
    vi.useFakeTimers()
    renderHarness(stalled())
    await act(async () => {})
    expect(latest.isLoading).toBe(true)

    await act(async () => {
      vi.advanceTimersByTime(REQUEST_TIMEOUT_MS - 1)
    })
    expect(latest.isLoading).toBe(true)
    expect(latest.error).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(latest.isLoading).toBe(false)
    expect(latest.error).toBe('The Pulse server took too long to respond. Please try again.')
  })

  it('does not time out a request that answers in time', async () => {
    vi.useFakeTimers()
    renderHarness(() => Promise.resolve('figures'))
    await act(async () => {})
    await act(async () => {
      vi.advanceTimersByTime(REQUEST_TIMEOUT_MS * 2)
    })

    expect(latest.data).toBe('figures')
    expect(latest.error).toBeNull()
  })

  it('sends a 401 through the shared session-expiry flow, never as a page error', async () => {
    renderHarness(() => Promise.reject(new ApiRequestError(401, 'expired')))

    expect(await screen.findByText(/signed out/)).toBeInTheDocument()
    expect(screen.getByText(/your management session has expired/i)).toBeInTheDocument()
    expect(latest.error).toBeNull()
  })

  it.each([
    [new ApiRequestError(0, 'x'), 'Could not reach the Pulse server. Check your connection and try again.'],
    [new ApiRequestError(503, 'raw server text'), 'The data is temporarily unavailable. Please try again shortly.'],
    [new ApiRequestError(422, "'Nowhere' is not a known Production Line."), "'Nowhere' is not a known Production Line."],
    [new Error('raw'), 'The data could not be loaded. Please try again.'],
  ])('shows a safe message for %s', async (error, message) => {
    renderHarness(() => Promise.reject(error))

    expect(await screen.findByText(new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeInTheDocument()
  })

  it('reload() asks again and keeps the old data visible meanwhile', async () => {
    const load = vi.fn<Loader>().mockResolvedValueOnce('first').mockResolvedValueOnce('second')
    renderHarness(load)
    expect(await screen.findByText(/first/)).toBeInTheDocument()

    act(() => latest.reload())
    expect(latest.data).toBe('first')

    expect(await screen.findByText(/second/)).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('abandons a superseded request when the key changes, so stale data never lands', async () => {
    let resolveOld!: (value: string) => void
    const old: Loader = () => new Promise((resolve) => (resolveOld = resolve))
    const { rerenderWith } = renderHarness(old, 'line=GIC')
    await act(async () => {})

    rerenderWith(() => Promise.resolve('Rovema figures'), 'line=Rovema')
    expect(await screen.findByText(/Rovema figures/)).toBeInTheDocument()

    await act(async () => resolveOld('stale GIC figures'))
    expect(latest.data).toBe('Rovema figures')
  })
})
