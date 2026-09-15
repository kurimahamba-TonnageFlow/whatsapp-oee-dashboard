import { joinUrl } from '../utils/joinUrl'

/**
 * Thrown for any non-2xx response. `message` is always a safe,
 * user-facing string - either the backend's own pre-written `detail`
 * (FastAPI never puts exception text, connection strings, or
 * credentials there - see docs/*_integration.md) or a generic
 * fallback, never a raw error dump.
 */
export class ApiRequestError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

export interface RequestOptions {
  token?: string
  signal?: AbortSignal
}

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? ''
}

function extractDetail(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return null
}

async function request<T>(
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`
  }

  let response: Response
  try {
    response = await fetch(joinUrl(getApiBaseUrl(), path), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
  } catch {
    throw new ApiRequestError(0, 'Could not reach the API. Check your connection and try again.')
  }

  let data: unknown = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      extractDetail(data) ?? 'The request could not be completed. Please try again.',
    )
  }

  return data as T
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PATCH', path, body, options),
}
