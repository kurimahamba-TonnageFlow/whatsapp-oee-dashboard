import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { TargetSpeedScreen } from './TargetSpeedScreen'
import { runState } from '../hmiTestState'

it('retrospective operating setting leaves the displayed standard fixed', () => {
  const state = runState()
  state.run.standard_speed_ppm = 100
  const submit = vi.fn()
  render(<TargetSpeedScreen state={state} isSubmitting={false} errorMessage={null} onCancel={() => {}} onSubmit={submit} />)
  expect(screen.getByText(/100 packs\/min/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/Operating speed \(packs/), {target:{value:'90'}})
  fireEvent.change(screen.getByLabelText(/Effective time/), {target:{value:'2026-01-12T06:30'}})
  fireEvent.change(screen.getByLabelText(/Reason for/), {target:{value:'Film trial'}})
  fireEvent.click(screen.getByRole('button',{name:'Save Operating Speed'}))
  expect(submit).toHaveBeenCalledWith('90','Film trial',new Date('2026-01-12T06:30').toISOString(),undefined)
  expect(screen.getByText(/100 packs\/min/)).toBeInTheDocument()
})

it('correction retains the identity of the original evidence', () => {
  const state=runState()
  state.operating_speed_changes=[{change_id:12,previous_speed_ppm:null,new_speed_ppm:90,reason:'Film',changed_by:'Liam',effective_at:'2026-01-12T06:30:00Z'}]
  const submit=vi.fn()
  render(<TargetSpeedScreen state={state} isSubmitting={false} errorMessage={null} onCancel={() => {}} onSubmit={submit} />)
  fireEvent.click(screen.getByRole('button',{name:'Correct this record'}))
  fireEvent.change(screen.getByLabelText(/Reason for/),{target:{value:'Correcting the setting'}})
  fireEvent.click(screen.getByRole('button',{name:'Save Operating Speed'}))
  expect(submit).toHaveBeenCalledWith('90','Correcting the setting','2026-01-12T06:30:00.000Z',12)
})
