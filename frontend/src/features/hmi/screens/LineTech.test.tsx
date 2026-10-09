import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { LineTechFaultScreen } from './LineTechFaultScreen'
import { PlannedDowntimeScreen } from './PlannedDowntimeScreen'
import { LineTechChangeoverScreen } from './LineTechChangeoverScreen'
import { apiClient } from '../../../api/client'
import type { LineTechConfig } from '../linetech'
import type { HmiConfigMachine } from '../../../types/api'

vi.mock('../../../api/client',()=>({apiClient:{get:vi.fn(),post:vi.fn()}}))
const config:LineTechConfig={enabled:true,groups:[
 {key:'sbs',label:'SBS / Bagger',equipment:[1,2].map(id=>({machine_id:id,label:`BV${id}`,active:true,categories:[{name:'Film',active:true,button_ids:[id]}]}))},
 {key:'xray',label:'X-ray',equipment:[{machine_id:3,label:'X-ray',active:true,categories:[{name:'Faults',active:true,button_ids:[3]}]}]},
 {key:'casepacker',label:'Case Packer',equipment:[{machine_id:4,label:'Case Packer',active:true,categories:[{name:'Faults',active:true,button_ids:[4]}]}]},
 {key:'robot',label:'Robot Palletiser',equipment:[{machine_id:5,label:'Robot',active:true,categories:[{name:'Faults',active:true,button_ids:[5]}]}]},
 ],planned:[{reason:'Film Change',components:['BV1','BV2'],active:true},{reason:'Label Change',components:['Label 1','Label 2'],active:true},{reason:'CCP Check',components:[],active:true}],
 products:['White Basmati','Brown Basmati'],formats:['1 kg x 10','1 kg x 8'],sizes:['0.5','1','2'],product_engineering_required:false}
const machines:HmiConfigMachine[]=[1,2,3,4,5].map(id=>({id,name:id<3?`SBS Bagger BV${id}`:['','','','X-ray','Casepacker','Robot Palletiser'][id],buttons:[{id,name:id<3?'Film Torn':id===3?'Machine jam':id===4?'Infeed jam':'Dropping cases',event_type:'unplanned_fault',ownership:'Production',fault_category:null}]}))
beforeEach(()=>vi.clearAllMocks())
function tap(name:string){fireEvent.click(screen.getByRole('button',{name}))}
function fault(){const submit=vi.fn();render(<LineTechFaultScreen config={config} machines={machines} isSubmitting={false} errorMessage={null} onSubmit={submit} onCancel={vi.fn()}/>);return submit}

describe('LineTech fault navigation',()=>{
 it('shows exactly four configured machine groups',()=>{fault();expect(screen.getAllByRole('button')).toHaveLength(5);expect(screen.getByRole('button',{name:'SBS / Bagger'})).toBeInTheDocument()})
 it.each([['Case Packer','Infeed jam',4],['Robot Palletiser','Dropping cases',5],['X-ray','Machine jam',3]] as const)('reports %s in four taps without typing', (group,reason,id)=>{const submit=fault();tap(group);tap('Faults');tap(reason);tap('Report to Engineer');expect(submit).toHaveBeenCalledWith(expect.objectContaining({machineId:id,buttonId:id,reason,note:''}));expect(submit.mock.calls[0][0].restoredAt).toBeUndefined()})
 it.each([1,2])('retains the correct BV%s identity',id=>{const submit=fault();tap('SBS / Bagger');tap(`BV${id}`);tap('Film');tap('Film Torn');tap('Report to Engineer');expect(submit.mock.calls[0][0].machineId).toBe(id)})
 it('records resolved downtime only after explicit restart confirmation',()=>{const submit=fault();tap('SBS / Bagger');tap('BV1');tap('Film');tap('Film Torn');tap('Resolved by LineTech');expect(screen.getByRole('button',{name:'Save resolved downtime'})).toBeDisabled();fireEvent.click(screen.getByLabelText('Production has restarted now'));tap('Save resolved downtime');expect(submit.mock.calls[0][0]).toEqual(expect.objectContaining({note:'',startedAt:expect.any(String),restoredAt:expect.any(String)}))})
 it('requires a short Other Fault description but not a second note',()=>{const submit=fault();tap('Robot Palletiser');tap('Faults');tap('Other Fault');tap('Report to Engineer');expect(submit).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('Describe Other Fault'),{target:{value:'Gripper not releasing'}});tap('Report to Engineer');expect(submit.mock.calls[0][0]).toEqual(expect.objectContaining({buttonId:null,reason:'Gripper not releasing',note:'Gripper not releasing'}))})
 it('Back returns to the previous step without submitting',()=>{const submit=fault();tap('Case Packer');tap('Faults');tap('Infeed jam');tap('Back');expect(screen.getByRole('heading',{name:'Select fault'})).toBeInTheDocument();expect(submit).not.toHaveBeenCalled()})
})
describe('planned stop confirmation',()=>{
 it.each([['Film Change','BV1'],['Film Change','BV2'],['Label Change','Label 1'],['Label Change','Label 2'],['CCP Check',null]])('records %s / %s as one confirmed stop',(reason,component)=>{const start=vi.fn();render(<PlannedDowntimeScreen configuredReasons={config} reasons={[]} activeEvent={null} isSubmitting={false} errorMessage={null} onStart={start} onEnd={vi.fn()} onCancel={vi.fn()}/>);tap(reason);expect(start).not.toHaveBeenCalled();if(component)tap(component);tap('Confirm planned stop');expect(start).toHaveBeenCalledWith(reason,component??undefined);expect(screen.getByText(/does not record a passed quality or CCP check/)).toBeInTheDocument()})
})
describe('structured changeover',()=>{
 it.each([['Product','Brown Basmati','product'],['Format','1 kg x 8','format'],['Size','0.5 kg','size']] as const)('selects a configured %s changeover',(label,value,kind)=>{
  vi.mocked(apiClient.get).mockResolvedValue({config,previous:{product:'White Basmati',format:'1 kg x 10',pack_weight_kg:1}})
  const confirm=vi.fn();render(<LineTechChangeoverScreen line="Rovema" isSubmitting={false} errorMessage={null} onConfirm={confirm} onBack={vi.fn()}/>);
  return waitFor(()=>expect(screen.getByRole('button',{name:label})).not.toBeDisabled()).then(()=>{tap(label);tap(value);tap('Confirm Changeover');expect(confirm).toHaveBeenCalledWith({kind,next_value:kind==='size'?'0.5':value})})
 })
})
