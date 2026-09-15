import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient, ApiRequestError } from './client'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  fetchMock.mockReset()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('apiClient', () => {
  it('returns parsed JSON on a successful GET', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 'ok' }))

    const result = await apiClient.get<{ status: string }>('/health')

    expect(result).toEqual({ status: 'ok' })
  })

  it('sends a JSON body and Authorization header on POST when given a token', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { run_id: 1 }))

    await apiClient.post('/api/v1/runs', { production_line: 'Rovema' }, { token: 'abc' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ production_line: 'Rovema' }))
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc')
  })

  it('throws a safe ApiRequestError using the response detail on failure', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { detail: 'Dashboard data is temporarily unavailable.' }),
    )

    await expect(apiClient.get('/api/v1/dashboard/summary')).rejects.toMatchObject({
      status: 503,
      message: 'Dashboard data is temporarily unavailable.',
    })
  })

  it('falls back to a generic message when the error body has no string detail', async () => {
    fetchMock.mockResolvedValue(jsonResponse(422, { detail: [{ msg: 'invalid' }] }))

    await expect(apiClient.get('/api/v1/runs')).rejects.toMatchObject({
      status: 422,
      message: 'The request could not be completed. Please try again.',
    })
  })

  it('wraps a network failure as a safe ApiRequestError, never a raw error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(apiClient.get('/health')).rejects.toBeInstanceOf(ApiRequestError)
    await expect(apiClient.get('/health')).rejects.toMatchObject({
      status: 0,
      message: 'Could not reach the API. Check your connection and try again.',
    })
  })

  it('handles a missing VITE_API_BASE_URL safely by falling back to a relative request', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 'ok' }))

    await apiClient.get('/health')

    expect(fetchMock).toHaveBeenCalledWith('/health', expect.any(Object))
  })

  it('forwards an AbortSignal to fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 'ok' }))
    const controller = new AbortController()

    await apiClient.get('/health', { signal: controller.signal })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.signal).toBe(controller.signal)
  })
})
