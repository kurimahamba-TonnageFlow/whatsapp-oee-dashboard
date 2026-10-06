import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ReportToEngineerScreen } from './ReportToEngineerScreen'
import type { HmiConfigMachine } from '../../../types/api'
const button = (id: number, name: string) => ({ id, name, event_type: 'unplanned_fault' as const, ownership: 'Production' as const, fault_category: null })
const machines: HmiConfigMachine[] = [
 { id: 1, name: 'SBS Bagger BV1', buttons: [button(11, 'Film torn'), button(12, 'Bag crosswise')] },
 { id: 2, name: 'SBS Bagger BV2', buttons: [button(21, 'Film torn')] },
 { id: 3, name: 'SBS Shared Equipment', buttons: [button(31, 'SBS discharge belt jam'), button(32, 'Secondary jaw cut-off extractor fault'), button(33, 'Top fold guide fault')] },
]
function open() {
 const onSubmit = vi.fn()
 render(<ReportToEngineerScreen productionLine="Rovema" machines={machines} isSubmitting={false} result={null} errorMessage={null} onSubmit={onSubmit} onCancel={vi.fn()} onDone={vi.fn()} />)
 fireEvent.click(screen.getByRole('button', { name: 'SBS' }))
 return onSubmit
}
it('keeps identical BV1 and BV2 fault labels attached to different database IDs', () => {
 const save = open()
 fireEvent.click(screen.getByRole('button', { name: 'BV2' }))
 fireEvent.click(screen.getByRole('button', { name: 'Film' }))
 fireEvent.click(screen.getByRole('button', { name: 'Film torn' }))
 fireEvent.click(screen.getByRole('button', { name: 'Report to Engineer' }))
 expect(save).toHaveBeenCalledWith(expect.objectContaining({ machine: 'SBS Bagger BV2', machineId: 2, buttonId: 21, reason: 'Film torn', note: 'Section: Film' }))
 expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})
it('clears section and fault selection when changing from BV1 to shared SBS equipment', () => {
 const save = open()
 fireEvent.click(screen.getByRole('button', { name: 'BV1' }))
 fireEvent.click(screen.getByRole('button', { name: 'Film' }))
 fireEvent.click(screen.getByRole('button', { name: 'Film torn' }))
 fireEvent.click(screen.getByRole('button', { name: 'Shared SBS equipment' }))
 fireEvent.click(screen.getByRole('button', { name: 'Report to Engineer' }))
 expect(save).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button', { name: 'Discharge belts' }))
 fireEvent.click(screen.getByRole('button', { name: 'SBS discharge belt jam' }))
 fireEvent.click(screen.getByRole('button', { name: 'Report to Engineer' }))
 expect(save).toHaveBeenCalledWith(expect.objectContaining({ machine: 'SBS Shared Equipment', machineId: 3, buttonId: 31 }))
})
it('keeps an Other fault under its selected equipment and requires written detail', () => {
 const save = open()
 fireEvent.click(screen.getByRole('button', { name: 'BV1' }))
 fireEvent.click(screen.getByRole('button', { name: 'Bagger forming section' }))
 fireEvent.click(screen.getByRole('button', { name: 'Other fault reason' }))
 fireEvent.change(screen.getByLabelText('Describe the fault'), { target: { value: 'Forming problem' } })
 fireEvent.click(screen.getByRole('button', { name: 'Report to Engineer' }))
 expect(save).not.toHaveBeenCalled()
 fireEvent.change(screen.getByLabelText('Note (required)'), { target: { value: 'Pack catches on guide' } })
 fireEvent.click(screen.getByRole('button', { name: 'Report to Engineer' }))
 expect(save).toHaveBeenCalledWith(expect.objectContaining({ machineId: 1, buttonId: null, reason: 'Bagger forming section: Forming problem', note: 'Section: Bagger forming section\nPack catches on guide' }))
})
