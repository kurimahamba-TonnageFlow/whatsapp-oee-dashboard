import { useState, type FormEvent } from 'react'
import catalogue from '../../../../src/production_catalogue.json'
import { LINE_TECHNICIANS, PRODUCTS } from './constants'
import { apiClient, ApiRequestError } from '../../api/client'
const STORAGE='pulse.task-observation.pending.v1'
interface Pending {key:string; body: Record<string, unknown>}
function pending(): Pending | null {const raw=localStorage.getItem(STORAGE);if(!raw)return null;const value=JSON.parse(raw) as Pending;if(!value.key || !value.body)throw new Error('Invalid pending task');return value}
export function TaskCapture() {
 const [saved,setSaved]=useState<Pending|null>(()=>{try{return pending()}catch{return null}})
 const [busy,setBusy]=useState(false)
 const [message,setMessage]=useState('')
 const [conflict,setConflict]=useState(false)
 async function submit(record:Pending){
  if(busy)return
  setBusy(true);setMessage('');setConflict(false)
  try{await apiClient.post('/api/v1/task-observations',record.body,{idempotencyKey:record.key});localStorage.removeItem(STORAGE);setSaved(null);setMessage('Task observation saved. Production downtime and output were not changed.')}
  catch(e){if(e instanceof ApiRequestError && e.status===409)setConflict(true);if(e instanceof ApiRequestError && [400,422].includes(e.status)){localStorage.removeItem(STORAGE);setSaved(null)}setMessage(e instanceof Error?e.message:'Could not confirm save. Retry the pending observation.')}
  finally{setBusy(false)}
 }
 async function save(event:FormEvent<HTMLFormElement>){
  event.preventDefault();if(busy)return
  const values=new FormData(event.currentTarget)
  try{
   const previous=pending();if(previous){setSaved(previous);setMessage('Confirm the pending observation first.');return}
   const body={production_line:'Rovema',task:values.get('task'),technician:values.get('technician'),product:values.get('product'),
    from_configuration:values.get('from_configuration'),to_configuration:values.get('to_configuration'),
    started_at:new Date(String(values.get('started_at'))).toISOString(),ended_at:new Date(String(values.get('ended_at'))).toISOString(),
    waiting_minutes:Number(values.get('waiting_minutes')),shared_work:values.get('shared_work')==='yes',completed_successfully:values.get('completed_successfully')==='yes',notes:values.get('notes')}
   const record={key:crypto.randomUUID(),body};localStorage.setItem(STORAGE,JSON.stringify(record));setSaved(record);await submit(record)
  }catch{setMessage('Could not preserve valid task details on this device. Nothing new was sent.')}
 }
 return <details className="pulse-panel"><summary>Record task - Rovema</summary><h2>Completed task observation</h2>
 <p>For timing evidence only. This does not start or stop production downtime. Record actual start and finish, the person who performed the task and any waiting or shared work.</p>
 <p>Times use this device's timezone. Check that the tablet is set to Europe/London. Configuration should include product/format, pack weight, packs per case and cases per pallet; describe both sides of a changeover.</p>
 {saved&&<section aria-label="Pending task observation"><p>A task submission is unconfirmed. Retry the same observation after reconnecting.</p><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(saved.body,null,2)}</pre><button type="button" disabled={busy} onClick={()=>void submit(saved)}>Confirm pending task</button>{conflict&&<button type="button" onClick={()=>{localStorage.removeItem(STORAGE);setSaved(null);setConflict(false);setMessage("Rejected submission cleared locally. Existing recorded evidence is unchanged.")}}>Clear rejected submission</button>}</section>}
 <form onSubmit={save}><fieldset disabled={busy||!!saved} className="hmi-form-grid"><legend>Rovema task details</legend>
 <label className="hmi-field">Task<select name="task" required><option value="">Select task</option>{catalogue.tasks.map(t=><option key={t}>{t}</option>)}</select></label>
 <label className="hmi-field">Performed by<select name="technician" required><option value="">Select technician</option>{LINE_TECHNICIANS.map(t=><option key={t}>{t}</option>)}</select></label>
 <label className="hmi-field">Task product<select name="product" required><option value="">Select product</option>{PRODUCTS.map(p=><option key={p}>{p}</option>)}</select></label>
 <label className="hmi-field">Starting configuration<input name="from_configuration" required maxLength={300}/></label>
 <label className="hmi-field">Finishing configuration<input name="to_configuration" required maxLength={300}/></label>
 <label className="hmi-field">Task started<input name="started_at" type="datetime-local" required/></label>
 <label className="hmi-field">Task finished<input name="ended_at" type="datetime-local" required/></label>
 <label className="hmi-field">Waiting minutes<input name="waiting_minutes" type="number" min="0" step="0.01" required/></label>
 <label className="hmi-field">Was this shared work?<select name="shared_work" required><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select></label>
 <label className="hmi-field">Completed successfully?<select name="completed_successfully" required><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select></label>
 <label className="hmi-field">Task context / delays<textarea name="notes" maxLength={2000}/></label>
 <button type="submit">Save task observation</button></fieldset></form>{message&&<p role="status">{message}</p>}</details>
}
