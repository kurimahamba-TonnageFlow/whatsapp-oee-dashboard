import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { apiClient } from '../../api/client'
import { ProductionStandards } from './ProductionStandards'
vi.mock('./session/useManagementSession',()=>({useManagementSession:()=>({session:{token:'manager-session',managerName:'Kuri'},handleAuthError:()=>false})}))
vi.mock('./session/useProtectedData',()=>({useProtectedData:()=>({data:[],error:null,isLoading:false,reload:vi.fn()})}))
afterEach(()=>{vi.restoreAllMocks();localStorage.clear()})

it('records management standard with effective time and retries the same request key',async()=>{
 const post=vi.spyOn(apiClient,'post').mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({id:7})
 render(<MemoryRouter><ProductionStandards/></MemoryRouter>)
 for (const [label,value] of [[/^Product$/,'Rice'],[/Pack format/,'Pillow'],[/Nominal pack weight/,'1'],[/Packs per case/,'10'],[/Cases per pallet/,'100'],[/Management standard \(packs/,'130'],[/Effective time/,'2026-10-05T06:00'],[/^Reason$/,'Approved baseline']] as const) {
  fireEvent.change(screen.getByLabelText(label),{target:{value}})
 }
 fireEvent.click(screen.getByRole('button',{name:'Save standard'}))
 await screen.findByText('Connection lost')
 fireEvent.click(screen.getByRole('button',{name:'Save standard'}))
 await waitFor(()=>expect(post).toHaveBeenCalledTimes(2))
 expect(post.mock.calls[0]).toEqual(post.mock.calls[1])
 expect(post.mock.calls[0][1]).toMatchObject({standard_speed_ppm:'130',reason:'Approved baseline',effective_at:new Date('2026-10-05T06:00').toISOString()})
 expect(post.mock.calls[0][2]).toMatchObject({token:'manager-session'})
 await screen.findByText(/Existing runs keep their standard/)
})

it('recovers the exact pending standard after a page remount',async()=>{
 const body={production_line:'Rovema',product:'Rice',standard_speed_ppm:'130',reason:'Approved'}
 localStorage.setItem('pulse.management.pending-standard.v1',JSON.stringify({body:JSON.stringify(body),key:'durable-key',manager:'Kuri'}))
 const post=vi.spyOn(apiClient,'post').mockResolvedValue({id:9})
 render(<MemoryRouter><ProductionStandards/></MemoryRouter>)
 fireEvent.click(screen.getByRole('button',{name:'Confirm pending standard'}))
 await waitFor(()=>expect(post).toHaveBeenCalled())
 expect(post.mock.calls[0][1]).toEqual(body)
 expect(post.mock.calls[0][2]).toMatchObject({idempotencyKey:'durable-key'})
 await waitFor(()=>expect(localStorage.getItem('pulse.management.pending-standard.v1')).toBeNull())
})
