import { engineeringWorkMinutes } from '../../engineering/changeoverTimes'
import { useEffect, useState } from 'react'
import { ApiRequestError, apiClient } from '../../../api/client'
import { getCasepackerStatus, type CasepackerRequest } from '../../engineering/casepackerApi'
import type { ChangeoverWorkflow } from '../linetech'
import type { ActiveLineStoppage } from './LineStoppageScreen'
import { LINE_TECHNICIANS } from '../constants'

type Context={changeover:{workflow:ChangeoverWorkflow|null;physical_ended_at:string|null;restarted_at:string|null}|null}
type Pending={path:string;body:Record<string,unknown>;key:string}
export function LineTechStoppageScreen({stoppage,isSubmitting,errorMessage,onEnd,onStartNewRun,onHome}:{
 stoppage:ActiveLineStoppage;isSubmitting:boolean;errorMessage:string|null;onEnd:(actor:string)=>void;onStartNewRun:()=>void;onHome:()=>void;
}) {
 const [data,setData]=useState<Context|null>(null);const [job,setJob]=useState<CasepackerRequest|null>(null)
 const [saveError,setSaveError]=useState('');
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [now,setNow]=useState(Date.now())
 const [actor,setActor]=useState(stoppage.startedBy??'');const [reference,setReference]=useState('')
 const [checks,setChecks]=useState({first_off:false,label:false,date_code:false,ccp:false})
 const [cancelOpen,setCancelOpen]=useState(false);const [reason,setReason]=useState('');const [reload,setReload]=useState(0)
 const pendingKey=`pulse.linetech.changeover.${stoppage.stoppageId}`
 const [pending,setPending]=useState<Pending|null>(()=>{try{return JSON.parse(sessionStorage.getItem(pendingKey)??'null') as Pending|null}catch{return null}})
 useEffect(()=>{const c=new AbortController();let loading=false;const load=async()=>{if(loading)return;loading=true;try{const [context,status]=await Promise.all([apiClient.get<Context>(`/api/v1/line-stoppages/${stoppage.stoppageId}/linetech`,{signal:c.signal}),getCasepackerStatus(stoppage.stoppageId,c.signal)]);if(!c.signal.aborted){setData(context);setJob(status.request);setError('');setNow(Date.now())}}catch{if(!c.signal.aborted)setError('Could not check current status. Restart is blocked until reconnected.')}finally{loading=false}};void load();const timer=setInterval(()=>void load(),5000);return()=>{c.abort();clearInterval(timer)}},[stoppage.stoppageId,stoppage.physicalEndedAt,reload])
 const workflow=data?.changeover?.workflow
 const cancelled=!!workflow?.cancelled_at
 const physical=!!data?.changeover?.physical_ended_at
 const workReady=!job || !!job.ready_at || !!job.cancelled_at
 const verified=workflow?.qa_status==='verified'
 async function send(action:Pending) {
  if(busy)return;setBusy(true);setSaveError('')
  try{sessionStorage.setItem(pendingKey,JSON.stringify(action));setPending(action);await apiClient.post(action.path,action.body,{idempotencyKey:action.key});sessionStorage.removeItem(pendingKey);setPending(null);setReload(r=>r+1)}catch(e){setSaveError(e instanceof Error?e.message:'Could not confirm save. Retry the original action.');if(e instanceof ApiRequestError && e.status>=400 && e.status<500){sessionStorage.removeItem(pendingKey);setPending(null)}}finally{setBusy(false)}
 }
 function action(suffix:string,body:Record<string,unknown>){void send(pending??{path:`/api/v1/line-stoppages/${stoppage.stoppageId}/${suffix}`,body,key:crypto.randomUUID()})}
 const disabled=busy||isSubmitting||!!pending
 const minutes=(a:string,b:string|number)=>Math.max(0,((typeof b==='number'?b:Date.parse(b))-Date.parse(a))/60000).toFixed(1)
 return <div className="hmi-screen linetech-screen"><p className="linetech-eyebrow">CHANGEOVER · {stoppage.productionLine}</p>
  <h1>{cancelled?'Changeover cancelled':workflow?`${workflow.kind[0].toUpperCase()+workflow.kind.slice(1)} changeover`:'Changeover'}</h1>
  {workflow&&<p>{workflow.previous_value} → {workflow.next_value}{workflow.kind==='size'?' kg':''}</p>}
  <div className="linetech-clocks"><div>Production stopped<strong>{minutes(stoppage.startedAt,now)} min</strong></div>
   <div>Engineering response<strong>{job?`${minutes(job.requested_at,job.first_accepted_at??job.accepted_at??job.cancelled_at??now)} min`:'Not required'}</strong></div>
   <div>Engineering work<strong>{job && engineeringWorkMinutes(job,now)!==null?`${engineeringWorkMinutes(job,now)!.toFixed(1)} min`:'Not started'}</strong></div></div>
  <div className={`linetech-confirm ${verified ? "linetech-status-good" : "linetech-status-waiting"}`} role="status"><h2>{cancelled?'Cancelled — production stop still running':!data?'Checking status…':!workReady?job?.engineer?'Engineering in progress':'Waiting for Engineering':!physical?'Work complete — confirm physical changeover':!verified?'Awaiting verification':'Verified — ready for new run setup'}</h2>
   {job&&<><p>{job.details}</p><p>{job.engineer?`Engineer: ${job.engineer}`:'Engineering request sent.'}</p></>}
   <p>The production clock stops only when the next run actually starts.</p>
  </div>
  <label className="hmi-field">Line technician<select value={actor} disabled={disabled} onChange={e=>setActor(e.target.value)}><option value="">Select technician</option>{LINE_TECHNICIANS.map(n=><option key={n}>{n}</option>)}</select></label>
  {!cancelled && !physical && <button className="hmi-primary-button" disabled={disabled||!actor||!data||!!error||!workReady} onClick={()=>onEnd(actor)}>Confirm physical changeover complete</button>}
  {!cancelled && physical && workReady && !verified && <fieldset disabled={disabled} className="linetech-confirm"><legend>Record verification</legend><p>Confirm the actual QA checks and record their reference. This screen does not perform or automatically pass the checks.</p>
   <div className="linetech-check-grid">{(Object.keys(checks) as (keyof typeof checks)[]).map(k=><label className="linetech-check" key={k}><input type="checkbox" checked={checks[k]} onChange={e=>setChecks({...checks,[k]:e.target.checked})}/>{{first_off:'First-off approved',label:'Label checked',date_code:'Date code checked',ccp:'CCP check passed'}[k]}</label>)}</div>
   <label className="hmi-field">QA record reference<input value={reference} maxLength={500} onChange={e=>setReference(e.target.value)}/></label>
   <button className="hmi-primary-button" disabled={!actor||!reference.trim()||!Object.values(checks).every(Boolean)} onClick={()=>action('verification',{technician:actor,...checks,reference:reference.trim()})}>Save verification</button>
  </fieldset>}
  {(verified||cancelled)&&<button className="hmi-primary-button" disabled={disabled||!data||!!error||!workReady} onClick={onStartNewRun}>Enter New Run Details</button>}
  {cancelled&&<p>Cancelled by {workflow?.cancelled_by}: {workflow?.cancellation_reason}. Check the line configuration before starting another run.</p>}
  {!cancelled&&!verified&&<><button className="hmi-secondary-button" disabled={disabled} onClick={()=>setCancelOpen(!cancelOpen)}>Cancel changeover</button>{cancelOpen&&<div className="linetech-confirm"><p>Cancel the intended change and its Engineering job. The production stop stays open until a new run starts.</p><label className="hmi-field">Cancellation reason<input maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label><button className="hmi-danger-button" disabled={disabled||!actor||!reason.trim()} onClick={()=>action('cancel',{technician:actor,reason:reason.trim()})}>Confirm cancellation</button></div>}</>}
  {(saveError||error||errorMessage)&&<p role="alert">{saveError||error||errorMessage}</p>}{pending&&<button className="hmi-primary-button" disabled={busy} onClick={()=>void send(pending)}>Retry original action</button>}
  <button className="hmi-secondary-button" onClick={onHome}>Home</button>
 </div>
}
