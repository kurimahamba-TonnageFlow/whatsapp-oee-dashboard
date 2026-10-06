import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { OperatingContext } from './OperatingContext'

it('shows period, speed, reporter, reason and correction audit without assigning loss', () => {
  render(<OperatingContext reports={[{period_start:'2026-01-12T06:00:00Z',period_end:'2026-01-12T07:00:00Z',speed_ppm:110,effective_at:'2026-01-12T06:30:00Z',submitted_at:'2026-01-12T06:45:00Z',changed_by:'Liam',reason:'Film tracking',supersedes_id:12}]} />)
  expect(screen.getByText(/110 packs\/minute reported by Liam/)).toHaveTextContent('Film tracking')
  expect(screen.getByText(/Corrects report 12/)).toHaveTextContent('2026-01-12T06:30:00Z')
  expect(screen.getByText(/They do not allocate the production gap/)).toBeInTheDocument()
})
