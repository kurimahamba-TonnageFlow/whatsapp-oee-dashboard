import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiStatus } from './ApiStatus'
import { apiClient } from '../api/client'

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn() },
}))

afterEach(() => {
  vi.resetAllMocks()
})

describe('ApiStatus', () => {
  it('shows a loading state before the health check resolves', () => {
    vi.mocked(apiClient.get).mockReturnValue(new Promise(() => {}))

    render(<ApiStatus />)

    expect(screen.getByText(/checking api/i)).toBeInTheDocument()
  })

  it('shows connected when the health check succeeds', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ status: 'ok', service: 'whatsapp-webhook' })

    render(<ApiStatus />)

    await waitFor(() => expect(screen.getByText(/api connected/i)).toBeInTheDocument())
  })

  it('shows unavailable when the health check fails, and still renders', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('network error'))

    render(<ApiStatus />)

    await waitFor(() => expect(screen.getByText(/api unavailable/i)).toBeInTheDocument())
  })
})
