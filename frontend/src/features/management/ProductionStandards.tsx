import './production-standards.css'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, apiClient } from '../../api/client'
import { useManagementSession } from './session/useManagementSession'
import { useProtectedData } from './session/useProtectedData'

interface StandardVersion {
 id: number; production_line: string; product: string | null; pack_type: string | null;
 pack_weight_kg: number; packs_per_case: number | null; cases_per_pallet: number | null;
 standard_speed_ppm: number; effective_at: string; recorded_at: string;
 manager_name: string; reason: string;
}

function localNow() {
 const now = new Date()
 return new Date(now.getTime() - now.getTimezoneOffset()*60000).toISOString().slice(0,16)
}

const PENDING_STANDARD = 'pulse.management.pending-standard.v1'
interface PendingStandard {body: string; key: string; manager: string}
function readPending(): PendingStandard | null {
 const raw=localStorage.getItem(PENDING_STANDARD)
 if(!raw)return null
 const value=JSON.parse(raw) as PendingStandard
 if(typeof value.body !== 'string' || typeof value.key !== 'string' || typeof value.manager !== 'string') throw new Error('Invalid pending standard record')
 JSON.parse(value.body)
 return value
}
export function ProductionStandards() {
 const {session, handleAuthError} = useManagementSession()
 const history = useProtectedData((token, signal) => apiClient.get<StandardVersion[]>('/api/v1/management/production-standards', {token, signal}), 'production-standards')
 const [busy,setBusy] = useState(false)
 const [message,setMessage] = useState('')
 const [pending,setPending] = useState<PendingStandard | null>(()=>{try{return readPending()}catch{return null}})
 async function submit(saved: PendingStandard) {
  if(!session || busy)return
  if(saved.manager !== session.managerName){setMessage('The manager who began this submission must sign in to confirm it.');return}
  setBusy(true);setMessage('')
  try {
   await apiClient.post('/api/v1/management/production-standards',JSON.parse(saved.body),{token:session.token,idempotencyKey:saved.key})
   localStorage.removeItem(PENDING_STANDARD);setPending(null)
   setMessage('Standard saved. It applies to new runs from its effective time. Existing runs keep their standard.');history.reload()
  } catch(error) {
   if(error instanceof ApiRequestError && [400,422].includes(error.status)){localStorage.removeItem(PENDING_STANDARD);setPending(null)}
   if(!handleAuthError(error))setMessage(error instanceof Error ? error.message : 'Could not confirm save. Retry the pending submission.')
  } finally {setBusy(false)}
 }
 async function save(event: FormEvent<HTMLFormElement>) {
  event.preventDefault()
  if (!session || busy) return
  const values = new FormData(event.currentTarget)
  const body = {production_line:String(values.get('production_line')), pack_weight_kg:String(values.get('pack_weight_kg')),
   standard_speed_ppm:String(values.get('standard_speed_ppm')),
   effective_at:new Date(String(values.get('effective_at'))).toISOString(), reason:String(values.get('reason'))}
  const encoded=JSON.stringify(body)
  try {
   const previous=readPending()
   if(previous && previous.body!==encoded){setPending(previous);setMessage('Confirm the pending submission before creating another standard.');return}
   const saved=previous ?? {body:encoded,key:crypto.randomUUID(),manager:session.managerName}
   localStorage.setItem(PENDING_STANDARD,JSON.stringify(saved));setPending(saved)
   await submit(saved)
  } catch {setMessage('Could not preserve this submission on the device. Nothing new was sent. Check browser storage.')}

 }
 return <section className="management-home production-standards">
  <Link to="/management">Back to Management</Link>
  <h1>Production standards</h1>
  <p>Set the standard speed for a line and pack weight. It applies to new runs from the date and time below. Existing runs and standard history are retained.</p>
  {pending && <section aria-label="Pending standard submission"><h2>Unconfirmed standard submission</h2><p>Started by {pending.manager}. Retry sends the original values and request key.</p>
   <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(JSON.parse(pending.body),null,2)}</pre>
   <button type="button" disabled={busy} onClick={()=>void submit(pending)}>Confirm pending standard</button></section>}
  <form onSubmit={save}>
   <fieldset disabled={busy} className="standards-grid"><legend>New standard version</legend>
    <label className="hmi-field">Production line<select name="production_line">{['Rovema','GIC','Guill'].map(x=><option key={x}>{x}</option>)}</select></label>
    <label className="hmi-field">Pack weight (kg)<input name="pack_weight_kg" type="number" required min="0.0001" step="0.0001"/></label>
    <label className="hmi-field">Speed (packs/min)<input name="standard_speed_ppm" type="number" required min="0.0001" max="10000" step="0.0001"/></label>
    <label className="hmi-field">Date and time changed (local)<input name="effective_at" type="datetime-local" defaultValue={localNow()} required/></label>
    <label className="hmi-field">Changed by<input value={session?.managerName ?? ''} readOnly/></label>
    <label className="hmi-field">Reason<textarea name="reason" required maxLength={500}/></label>
    <button className="standard-save" type="submit">{busy ? 'Saving...' : 'Save'}</button>
   </fieldset>
  </form>
  {message && <p role="status">{message}</p>}
  <h2>Version history</h2>
  {history.error && <p role="alert">{history.error}</p>}
  <button onClick={history.reload}>Refresh history</button>
  {history.isLoading && <p>Loading standards...</p>}
  {history.data?.length===0 && <p>No standards configured. Management must add one before starting a new run.</p>}
  {history.data?.map(r=><article key={r.id}>
   <h3>Version {r.id}: {r.production_line} / {r.pack_weight_kg} kg</h3>
   <p>Speed: {r.standard_speed_ppm} packs/min.</p>
   {r.product && <p>Earlier configuration: {r.product}, {r.pack_type}, {r.packs_per_case} packs/case, {r.cases_per_pallet} cases/pallet.</p>}
   <p>Effective {new Date(r.effective_at).toLocaleString()}. Recorded {new Date(r.recorded_at).toLocaleString()} by {r.manager_name}. Reason: {r.reason}</p>
  </article>)}
 </section>
}
