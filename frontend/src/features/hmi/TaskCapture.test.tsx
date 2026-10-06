import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, it, expect, vi } from 'vitest'
import { TaskCapture } from './TaskCapture'
import { apiClient } from '../../api/client'
afterEach(()=>{localStorage.clear();vi.restoreAllMocks()})
it('retains all seven tasks and replays a stored observation without changing its key',async()=>{
 const body={task:'Film Change',technician:'Liam',waiting_minutes:0}
 localStorage.setItem('pulse.task-observation.pending.v1',JSON.stringify({key:'original-key',body}))
 const post=vi.spyOn(apiClient,'post').mockResolvedValue({id:4})
 render(<TaskCapture/>);fireEvent.click(screen.getByText('Record task - Rovema'))
 expect(screen.getByLabelText('Task').querySelectorAll('option')).toHaveLength(8)
 fireEvent.click(screen.getByRole('button',{name:'Confirm pending task'}))
 await waitFor(()=>expect(post).toHaveBeenCalledWith('/api/v1/task-observations',body,{idempotencyKey:'original-key'}))
 await screen.findByText(/Task observation saved/)
 expect(localStorage.getItem('pulse.task-observation.pending.v1')).toBeNull()
})
