import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { apiClient, ApiRequestError } from '../../../api/client'
import { ProductionRestoreForm } from './ProductionRestoreForm'
import type { LineFault } from '../types'

afterEach(() => vi.restoreAllMocks())

it('requires details and retries an uncertain restart with the same time and key', async () => {
  const post = vi.spyOn(apiClient, 'post').mockRejectedValueOnce(new ApiRequestError(0, 'No reply')).mockResolvedValueOnce({})
  const refreshed = vi.fn()
  render(<ProductionRestoreForm fault={{ downtime_event_id: 8 } as LineFault} line="Rovema" technician="Liam" onRestored={refreshed} />)
  fireEvent.click(screen.getByRole('button', { name: 'Production restored' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm production restart' }))
  expect(post).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText(/actual restart time/i), { target: { value: '2026-01-12T06:10' } })
  fireEvent.change(screen.getByLabelText(/what was done/i), { target: { value: 'Cleared jam' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm production restart' }))
  await screen.findByText('No reply')
  expect(screen.getByLabelText(/actual restart time/i)).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm production restart' }))
  await waitFor(() => expect(refreshed).toHaveBeenCalledTimes(1))
  expect(post.mock.calls[1]).toEqual(post.mock.calls[0])
  expect(post.mock.calls[0][1]).toMatchObject({ technician: 'Liam', note: 'Cleared jam', restored_at: new Date('2026-01-12T06:10').toISOString() })
})
