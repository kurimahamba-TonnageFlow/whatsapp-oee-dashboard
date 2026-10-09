import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LineTechSetup } from './LineTechSetup'
import { apiClient } from '../../api/client'
import type { LineTechConfig } from '../hmi/linetech'

const auth=vi.hoisted(()=>({session:{token:'test'},handleAuthError:vi.fn(()=>false)}))
vi.mock('./session/useManagementSession',()=>({useManagementSession:()=>auth}))
vi.mock('../../api/client',()=>({apiClient:{get:vi.fn(),post:vi.fn(),patch:vi.fn()}}))
const machine={id:1,name:'BV1',active:true,buttons:[]}
let config:LineTechConfig
beforeEach(()=>{vi.resetAllMocks();config={enabled:false,products:[],sizes:[],formats:[],planned:[],product_engineering_required:false,groups:[{key:'sbs',label:'SBS / Bagger',equipment:[]},{key:'xray',label:'X-ray',equipment:[]}]}})
afterEach(cleanup)
async function setup(machines:typeof machine[]=[]){
 vi.mocked(apiClient.get).mockImplementation(async path=>(path.endsWith('/lines')?{items:[{id:1,name:'Rovema'}]}:{config,machines}) as never)
 vi.mocked(apiClient.post).mockResolvedValue({} as never)
 render(<MemoryRouter><LineTechSetup/></MemoryRouter>)
 await screen.findByText('Configuration for Rovema')
}
function equipment(){config.groups[0].equipment=[{machine_id:1,label:'BV1',active:true,categories:[]}]}
async function saved(){fireEvent.click(screen.getByRole('button',{name:'Save LineTech configuration'}));await waitFor(()=>expect(apiClient.post).toHaveBeenCalled());return vi.mocked(apiClient.post).mock.calls.find(c=>c[0].endsWith('/linetech'))?.[1] as LineTechConfig}
it('explains an empty catalogue and creates a machine inside its selected group',async()=>{
 await setup();expect(screen.getByText(/No machines are configured for Rovema/)).toBeInTheDocument()
 vi.mocked(apiClient.post).mockResolvedValue(machine as never)
 fireEvent.change(screen.getByLabelText('New machine in SBS / Bagger'),{target:{value:'BV1'}})
 fireEvent.click(screen.getByRole('button',{name:'Add machine to SBS / Bagger'}))
 await screen.findByText(/Machine created and assigned/)
 const result=await saved();expect(result.groups[0].equipment[0].machine_id).toBe(1)
})
it('offers assigned machines for moving and preserves their fault categories',async()=>{
 config.groups[1].equipment=[{machine_id:1,label:'BV1',active:true,categories:[{name:'Film',active:true,button_ids:[4]}]}]
 await setup([machine])
 const selects=screen.getAllByLabelText('Add or move existing machine to group')
 expect(within(selects[0]).getByRole('option',{name:/move from X-ray/})).toBeInTheDocument()
 fireEvent.change(selects[0],{target:{value:'1'}})
 const result=await saved();expect(result.groups[1].equipment).toEqual([]);expect(result.groups[0].equipment[0].categories[0].button_ids).toEqual([4])
})
it('routes a planned reason to the planned configuration without creating a fault',async()=>{
 equipment();await setup([machine])
 fireEvent.change(screen.getByLabelText('Downtime reason'),{target:{value:'Film Change'}})
 fireEvent.change(screen.getByLabelText('Downtime classification'),{target:{value:'planned'}})
 fireEvent.click(screen.getByRole('button',{name:'Add downtime reason'}))
 expect(apiClient.post).not.toHaveBeenCalled()
 const result=await saved();expect(result.planned).toEqual([{reason:'Film Change',components:['BV1'],active:true}]);expect(result.groups[0].equipment[0].categories).toEqual([])
})
it('creates and assigns an unplanned reason without dropping unsaved configuration',async()=>{
 equipment();await setup([machine])
 fireEvent.change(screen.getByLabelText('Formats'),{target:{value:'1 kg x 10'}})
 vi.mocked(apiClient.post).mockResolvedValue({id:5,name:'Film torn',active:true,event_type:'unplanned_fault'} as never)
 fireEvent.change(screen.getByLabelText('Downtime reason'),{target:{value:'Film torn'}})
 fireEvent.click(screen.getByRole('button',{name:'Add downtime reason'}))
 await screen.findByText(/Unplanned reason assigned/)
 expect(apiClient.post).toHaveBeenCalledWith('/api/v1/management/machines/1/buttons',expect.objectContaining({event_type:'unplanned_fault'}),expect.anything())
 const result=await saved();expect(result.groups[0].equipment[0].categories[0].button_ids).toEqual([5]);expect(result.formats).toEqual(['1 kg x 10']);expect(result.planned).toEqual([])
})
