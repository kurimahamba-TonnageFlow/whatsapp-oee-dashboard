import { MemoryRouter } from 'react-router-dom'
import { LineTechSetup } from '../src/features/management/LineTechSetup'
import { ManagementSessionContext, type ManagementSessionContextValue } from '../src/features/management/session/managementSessionContext'
/** Local visual fixture, excluded from the production entry point. No requests leave this page. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/styles/global.css'
import '../src/features/hmi/hmi.css'
import '../src/features/hmi/linetech.css'
import '../src/features/engineering/engineering.css'
import { ActiveRunScreen } from '../src/features/hmi/screens/ActiveRunScreen'
import { ReportToEngineerScreen } from '../src/features/hmi/screens/ReportToEngineerScreen'
import { PlannedDowntimeScreen } from '../src/features/hmi/screens/PlannedDowntimeScreen'
import { LineTechChangeoverScreen } from '../src/features/hmi/screens/LineTechChangeoverScreen'
import { LineTechStoppageScreen } from '../src/features/hmi/screens/LineTechStoppageScreen'
import { CasepackerQueue } from '../src/features/engineering/CasepackerQueue'
import { runState } from '../src/features/hmi/hmiTestState'
import { apiClient } from '../src/api/client'
import type { LineTechConfig, ChangeoverSelection, ChangeoverWorkflow } from '../src/features/hmi/linetech'
import type { HmiConfigMachine } from '../src/types/api'
import type { FaultReportResponse, PlannedDowntimeEvent } from '../src/features/hmi/types'
import type { CasepackerRequest } from '../src/features/engineering/casepackerApi'

if(!['localhost','127.0.0.1'].includes(location.hostname))throw new Error('This synthetic preview is local-only.')
const previewSession:ManagementSessionContextValue={session:{token:'synthetic-preview',managerName:'Preview manager',expiresAt:new Date(Date.now()+3600000).toISOString()},isRestoring:false,endReason:null,notice:null,signIn:()=>undefined,signOut:()=>undefined,expireSession:()=>undefined,acknowledgeSignOut:()=>undefined,handleAuthError:()=>false}
const now=()=>new Date().toISOString()
const ago=(m:number)=>new Date(Date.now()-m*60000).toISOString()
const names=['SBS Bagger BV1','SBS Bagger BV2','SBS Shared Equipment','X-ray / Checkweigher','Casepacker','Robot Palletiser']
const faults=[['Film Torn','Label Snapped','Top Seal','Vertical Seal','Bottom Seal','Bag Crosswise','Bag Printer','Ribbon Tension'],['Film Torn','Label Snapped','Top Seal','Vertical Seal','Bottom Seal','Bag Crosswise','Bag Printer','Ribbon Tension'],['SBS Discharge Belt Jam','Secondary Jaw Cut-off Extractor Fault','Top Fold Guide Fault'],['Machine jam','CCP check fail'],['Magazine pull error','Product positioning','Infeed jam','Cycle-chain overload','Main discharge conveyor','Pusher limit position','Gluing issues','Printer','Purge printer'],['Pallet stacker fault','Pallet outfeed transfer error','Infeed conveyor not moving','Incorrect stacking','Dropping cases','Safety sensor alarm','Pallet position','Wrapper']]
const machines:HmiConfigMachine[]=names.map((name,i)=>({id:i+1,name,buttons:faults[i].map((name,j)=>({id:(i+1)*100+j,name,event_type:'unplanned_fault',ownership:'Production',fault_category:null}))}))
const equipment=(index:number,label:string)=>({machine_id:index+1,label,active:true,categories:index<2?[
 {name:'Film',button_ids:[(index+1)*100],active:true},{name:'Sealing',button_ids:[2,3,4].map(n=>(index+1)*100+n),active:true},
 {name:'Printer and label',button_ids:[1,6,7].map(n=>(index+1)*100+n),active:true},{name:'Bag handling',button_ids:[(index+1)*100+5],active:true}
]:[{name:'Faults',button_ids:machines[index].buttons.map(b=>b.id),active:true}]})
const config:LineTechConfig={enabled:true,groups:[{key:'sbs',label:'SBS / Bagger',equipment:[equipment(0,'BV1'),equipment(1,'BV2'),equipment(2,'Shared equipment')]},{key:'xray',label:'X-ray',equipment:[equipment(3,'X-ray')]},{key:'casepacker',label:'Case Packer',equipment:[equipment(4,'Case Packer')]},{key:'robot',label:'Robot Palletiser',equipment:[equipment(5,'Robot Palletiser')]}],planned:[{reason:'Film Change',components:['BV1','BV2'],active:true},{reason:'Label Change',components:['Label 1','Label 2'],active:true},{reason:'CCP Check',components:[],active:true}],products:['White Basmati','Brown Basmati','White Long Grain'],sizes:['0.5','1','2'],formats:['1 kg x 10','1 kg x 8','500 g x 10'],product_engineering_required:false}
let workflow:ChangeoverWorkflow={kind:'format',next_value:'1 kg x 8',previous_value:'1 kg x 10',engineering_required:true,qa_status:'awaiting_verification',verification:null,cancelled_at:null}
let physical:string|null=null
let job:CasepackerRequest|null=null
const started=ago(12)
function begin(choice:ChangeoverSelection){workflow={...workflow,...choice,previous_value:choice.kind==='product'?'White Basmati':choice.kind==='size'?'1':'1 kg x 10',engineering_required:choice.kind!=='product',qa_status:'awaiting_verification',verification:null,cancelled_at:null};physical=null;job=choice.kind==='product'?null:{id:1,line_stoppage_id:1,production_line:'Rovema',details:`${choice.kind} changeover: ${workflow.previous_value} → ${choice.next_value}`,requested_by:'Liam',requested_at:ago(10),engineer:null,accepted_at:null,ready_at:null,updates:[],changeover_workflow:workflow}}
begin({kind:'format',next_value:'1 kg x 8'})
// These replacements are scoped to this preview entry only. Production uses the real client.
apiClient.get=async <T,>(path:string):Promise<T>=>{
 const response=path==='/api/v1/management/lines'?{items:[{id:1,name:'Rovema'}]}:path.startsWith('/api/v1/management/lines/')?{config,machines:machines.map(m=>({...m,active:true,buttons:m.buttons.map(b=>({...b,active:true}))}))}:path.endsWith('changeover-options')?{config,previous:{product:'White Basmati',format:'1 kg x 10',pack_weight_kg:1}}:path.endsWith('/linetech')?{changeover:{workflow,physical_ended_at:physical,restarted_at:null}}:path.endsWith('/casepacker')?{request:job}:path.endsWith('casepacker-requests')?{items:job?[job]:[]}:{}
 return response as T
}
apiClient.post=async <T,>(path:string,body?:unknown):Promise<T>=>{
 const input=body as Record<string,unknown>
 if(path.endsWith('/actions')&&job){const action=String(input.action);if(action==='accept'){job.engineer='Alfie';job.accepted_at=now();job.first_accepted_at??=job.accepted_at}if(action==='ready')job.ready_at=now();if(action==='handover'){job.engineer=null;job.accepted_at=null}job.updates.push({id:job.updates.length+1,action,engineer:'Alfie',note:String(input.note??''),created_at:now()})}
 if(path.endsWith('/verification'))workflow={...workflow,qa_status:'verified',verification:{technician:String(input.technician),reference:String(input.reference),recorded_at:now()}}
 if(path.endsWith('/cancel')){workflow={...workflow,cancelled_at:now(),cancelled_by:String(input.technician),cancellation_reason:String(input.reason)};if(job)job.cancelled_at=now();physical=now()}
 return {status:'success'} as T
}
export function Preview(){
 const [view,setView]=useState(new URLSearchParams(location.search).get('view')??'active');const [key,setKey]=useState(0)
 const [result,setResult]=useState<FaultReportResponse|null>(null);const [planned,setPlanned]=useState<PlannedDowntimeEvent|null>(null)
 const [message,setMessage]=useState('')
 const state=runState();state.generated_at=now();state.run.started_at=ago(60);state.run.pack_type='1 kg x 10';state.run.packs_per_case=10;state.run.cases_per_pallet=200;state.run.total_pallets_completed=3;state.run.pallets_remaining=35;state.progress.actual_packs=6000;state.progress.actual_tonnes=6;state.progress.output_gap_packs=1200;state.progress.pallets_recorded=3;state.progress.production_achievement_percent=83.3;state.run.customer='Aldi';state.run.format='1 kg x 10';state.run.standard_speed_ppm=120;state.progress.next_hourly_update_due_at=new Date(Date.now()+15*60000).toISOString()
 const navigate=(v:string)=>{setView(v);setKey(n=>n+1);setMessage('');setResult(null)}
 const no=()=>undefined
 return <><header style={{padding:'16px 24px',borderBottom:'1px solid #444c49',display:'flex',gap:20,justifyContent:'space-between',flexWrap:'wrap'}}><strong>TONNAGE FLOW / PULSE</strong><span style={{color:'#ffc04c'}}>LOCAL REVIEW · SYNTHETIC DATA · NO LIVE CONNECTION</span></header>
 <nav aria-label="Preview scenarios" style={{display:'flex',gap:8,padding:16,flexWrap:'wrap'}}>{['active','planned','fault','changeover','stoppage','engineering','management','before'].map(v=><button key={v} aria-pressed={view===v} onClick={()=>navigate(v)}>{v==='before'?'Breakdown':v[0].toUpperCase()+v.slice(1)}</button>)}</nav>
 <main key={key} style={{maxWidth:1200,margin:'0 auto',padding:'0 20px 32px'}}>{message&&<p role="status">{message}</p>}
 {view==='active'&&<ActiveRunScreen linetechEnabled state={state} isRefreshing={false} refreshError={null} pendingAction={null} onRefresh={no} onResolvePending={no} onDiscardPending={no} onHourlyUpdate={()=>setMessage('Existing hourly capture is unchanged.')} onPlannedDowntime={()=>navigate('planned')} onReportToEngineer={()=>navigate('fault')} onCompleteRun={()=>{setMessage('Preview: old run has ended. Select the next changeover.');setView('changeover')}} onExitRestart={no}/>}
 {(view==='fault'||view==='before')&&<ReportToEngineerScreen linetech={view==='fault'?config:undefined} productionLine="Rovema" machines={machines} isSubmitting={false} result={result} errorMessage={null} onCancel={()=>navigate('active')} onDone={()=>navigate('active')} onSubmit={input=>setResult({status:'success',downtime_event_id:901,production_run_id:901,production_line:'Rovema',fault_id:1,machine:input.machine,reason:input.reason,reported_by:'Liam',production_status:input.restoredAt?'Resolved':'Ongoing',engineering_status:'Not Started',opened_at:now(),linetech_resolved_at:input.restoredAt||input.awaitingRestart?now():null})}/>}
 {view==='planned'&&<PlannedDowntimeScreen configuredReasons={config} reasons={[]} activeEvent={planned} isSubmitting={false} errorMessage={null} onCancel={()=>navigate('active')} onStart={(reason,component)=>setPlanned({planned_downtime_id:901,production_run_id:901,production_line:'Rovema',reason,component,started_by:'Liam',started_at:now(),ended_by:null,ended_at:null,duration_minutes:null,is_active:true,elapsed_minutes:0})} onEnd={()=>{setPlanned(null);setMessage('Planned stop ended. No QA or CCP pass was recorded.')}}/>}
 {view==='changeover'&&<LineTechChangeoverScreen line="Rovema" isSubmitting={false} errorMessage={null} onBack={()=>navigate('active')} onConfirm={choice=>{begin(choice);navigate('stoppage')}}/>}
 {view==='stoppage'&&<LineTechStoppageScreen stoppage={{stoppageId:1,productionLine:'Rovema',kind:'changeover',reason:null,startedAt:started,startedBy:'Liam',endedAt:null,durationMinutes:null,physicalEndedAt:physical,linetech:true}} isSubmitting={false} errorMessage={null} onHome={()=>navigate('active')} onEnd={()=>{physical=now();setKey(n=>n+1)}} onStartNewRun={()=>setMessage('Preview: verification passed. Existing Start Run form follows; it must match the selected configuration.')}/>}
 {view==='management'&&<MemoryRouter><ManagementSessionContext.Provider value={previewSession}><LineTechSetup/></ManagementSessionContext.Provider></MemoryRouter>}
 {view==='engineering'&&<div className="engineering-screen"><CasepackerQueue token="synthetic-preview" engineerName="Alfie" onSessionExpired={no}/></div>}
 </main></>
}
createRoot(document.getElementById('root')!).render(<Preview/> )
