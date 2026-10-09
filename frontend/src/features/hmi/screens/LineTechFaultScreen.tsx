import { useState } from 'react'
import type { HmiConfigMachine } from '../../../types/api'
import type { LineTechConfig } from '../linetech'

export interface LineTechFaultInput {
 machine: string; machineId: number | null; buttonId: number | null; reason: string; note: string;
 startedAt?: string; restoredAt?: string; awaitingRestart?: boolean;
}
export function LineTechFaultScreen({config,machines,isSubmitting,errorMessage,onSubmit,onCancel}: {
 config: LineTechConfig; machines: HmiConfigMachine[]; isSubmitting: boolean; errorMessage: string|null;
 onSubmit: (input: LineTechFaultInput)=>void; onCancel: ()=>void;
}) {
 const [groupKey,setGroup] = useState('')
 const [machineId,setMachine] = useState<number|null>(null)
 const [categoryName,setCategory] = useState('')
 const [buttonId,setButton] = useState<number|null>(null)
 const [other,setOther] = useState(false)
 const [description,setDescription] = useState('')
 const [resolved,setResolved] = useState(false)
 const [note,setNote] = useState('')
 const [restart,setRestart] = useState(false)
 const [stopAt,setStopAt] = useState(()=>new Date().toISOString())
 const [error,setError] = useState('')
 const group = config.groups.find(g=>g.key===groupKey)
 const equipment = group?.equipment.filter(e=>e.active && machines.some(m=>m.id===e.machine_id)) ?? []
 const component = equipment.find(e=>e.machine_id===machineId)
 const machine = machines.find(m=>m.id===machineId)
 const categories = component?.categories.filter(c=>c.active) ?? []
 const category = categories.find(c=>c.name===categoryName)
 const buttons = machine?.buttons.filter(b=>b.event_type==='unplanned_fault' && category?.button_ids.includes(b.id)) ?? []
 const selected = buttons.find(b=>b.id===buttonId)
 function back() {
  setError('')
  if(resolved){setResolved(false);setRestart(false)}
  else if(selected || other){setButton(null);setOther(false)}
  else if(categoryName)setCategory('')
  else if(machineId && equipment.length>1)setMachine(null)
  else if(groupKey){setGroup('');setMachine(null)}
  else onCancel()
 }
 function submit(selfResolved: boolean, waiting = false) {
  if(!machine || (!selected && !description.trim())){setError('Describe the Other Fault before reporting.');return}
  if(selfResolved && !waiting && !restart){setError('Confirm that production has actually restarted.');return}
  onSubmit({machine:machine.name,machineId:machine.id,buttonId:selected?.id ?? null,
   reason:selected?.name ?? description.trim(), note:other ? description.trim() : note.trim(),
   ...(selfResolved ? waiting ? {startedAt:stopAt,awaitingRestart:true} : {startedAt:stopAt,restoredAt:new Date().toISOString()} : {})})
 }
 const stage = !group ? 'Select machine' : !component ? 'Select component' : !category ? 'Select category' : !selected && !other ? 'Select fault' : 'Choose action'
 return <div className="hmi-screen linetech-screen linetech-fault">
  <p className="linetech-eyebrow">UNPLANNED DOWNTIME</p><h1>{stage}</h1>
  <p className="linetech-breadcrumb">{[group?.label,component?.label,category?.name,selected?.name].filter(Boolean).join(' / ') || 'Tap the equipment that needs attention.'}</p>
  <fieldset disabled={isSubmitting} className="linetech-choices"><legend className="sr-only">{stage}</legend><div className="hmi-button-grid">
  {!group ? config.groups.map(g=><button key={g.key} className="linetech-tile" onClick={()=>{setGroup(g.key);const available=g.equipment.filter(e=>e.active && machines.some(m=>m.id===e.machine_id));setMachine(available.length===1?available[0].machine_id:null)}}>{g.label}</button>)
   : !component ? equipment.map(e=><button key={e.machine_id} className="linetech-tile" onClick={()=>setMachine(e.machine_id)}>{e.label}</button>)
   : !category ? <>{categories.map(c=><button key={c.name} className="linetech-tile" onClick={()=>setCategory(c.name)}>{c.name}</button>)}{!categories.length && <p>No active categories configured. Ask Management to configure this component.</p>}</>
   : !selected && !other ? <>{buttons.map(b=><button key={b.id} className="linetech-tile" onClick={()=>setButton(b.id)}>{b.name}</button>)}<button className="linetech-tile" onClick={()=>setOther(true)}>Other Fault</button></>
   : <>{other && <label className="hmi-field">Describe Other Fault<input value={description} maxLength={120} onChange={e=>setDescription(e.target.value)}/></label>}
    {!resolved ? <><button className="linetech-tile linetech-planned" onClick={()=>setResolved(true)}>Resolved by LineTech</button><button className="linetech-tile linetech-unplanned" onClick={()=>submit(false)}>Report to Engineer</button></>
    : <div className="linetech-confirm"><h2>Confirm production restart</h2><p>A repair alone does not end downtime.</p>
      <label className="hmi-field">Actual stop started<input type="datetime-local" value={localTime(stopAt)} onChange={e=>{if(e.target.value)setStopAt(new Date(e.target.value).toISOString())}}/></label>
      <p className="hmi-field-help">Defaults to when this screen opened. Correct it if the stop began earlier.</p>
      <label className="hmi-field">Comment (optional)<textarea value={note} onChange={e=>setNote(e.target.value)} maxLength={500}/></label>
      <button className="hmi-secondary-button" onClick={()=>submit(true,true)}>Repair complete ? still waiting to restart</button>
      <label className="linetech-check"><input type="checkbox" checked={restart} onChange={e=>setRestart(e.target.checked)}/>Production has restarted now</label>
      <button className="hmi-primary-button" onClick={()=>submit(true)} disabled={!restart}>Save resolved downtime</button>
    </div>}</>}
  </div></fieldset>
  {group && !equipment.length && <p role="status">No active equipment configured for this machine group.</p>}
  {(error || errorMessage) && <p role="alert" className="hmi-inline-error">{error || errorMessage}</p>}
  <button className="hmi-secondary-button" onClick={back} disabled={isSubmitting}>Back</button>
 </div>
}
function localTime(iso: string){const d=new Date(iso);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
