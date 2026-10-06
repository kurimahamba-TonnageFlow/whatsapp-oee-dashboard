import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { TaskPerformance } from './TaskPerformance'
vi.mock('../management/session/useProtectedData', () => ({useProtectedData: () => ({
  isLoading: false, error: null, reload: vi.fn(), data: {
    tasks: ['Film change'], technicians: ['Liam'], unclassified_count: 2,
    since: '2026-07-01T00:00:00Z', until: '2026-10-01T00:00:00Z',
    cells: [{technician: 'Liam', task: 'Film change', rating: 'grey', recorded_count: 0,
      status: 'No timed evidence', groups: [], evidence: []}],
  },
})}))
afterEach(cleanup)
it('shows neutral evidence cells and exposes missing evidence without rating controls', () => {
  render(<TaskPerformance />)
  fireEvent.click(screen.getByRole('button', {name: 'Liam, Film change: grey, 0 timers'}))
  expect(screen.getByText('No timed evidence recorded for this task.')).toBeInTheDocument()
  expect(screen.getByText(/Managers cannot assign colours/)).toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})
