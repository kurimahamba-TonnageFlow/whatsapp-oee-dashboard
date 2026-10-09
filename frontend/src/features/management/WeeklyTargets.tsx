import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useProtectedData } from './session/useProtectedData'
import { useManagementSession } from './session/useManagementSession'
import { getLive, saveLiveTarget } from '../dashboard/api'
import type { LiveSnapshot } from '../dashboard/liveTypes'
const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
function TargetForm({weekly,onSaved}:{weekly:LiveSnapshot['weekly'];onSaved:()=>void}){
 const {session,handleAuthError}=useManagementSession()
 const [start,setStart]=useState(weekly.week_start)
 const [day,setDay]=useState((new Date(weekly.week_start+'T12:00:00Z').getUTCDay()+6)%7)
 const [target,setTarget]=useState(weekly.target_tonnes?.toString()??'')
 const [notes,setNotes]=useState(weekly.notes)
 const [busy,setBusy]=useState(false);const [message,setMessage]=useState('')
 return <form className="linetech-choices" onSubmit={async e=>{e.preventDefault();if(!session||busy)return;setBusy(true);setMessage('');try{await saveLiveTarget(session.token,{site:'site',week_start:start,week_start_day:day,target_tonnes:Number(target),notes});setMessage('Weekly target saved. The live dashboard will refresh automatically.');onSaved()}catch(error){if(!handleAuthError(error))setMessage(error instanceof Error?error.message:'Could not save target.')}finally{setBusy(false)}}}>
 <fieldset disabled={busy}><legend>Weekly production target</legend><label className="hmi-field">Factory / site<select value="site" disabled><option value="site">This factory (all configured lines)</option></select></label><label className="hmi-field">Week starts on<select value={day} onChange={e=>setDay(Number(e.target.value))}>{DAYS.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></label><label className="hmi-field">Effective week start<input type="date" value={start} required onChange={e=>setStart(e.target.value)}/></label><p>The reporting week starts at 06:00 Europe/London on this date. Choose a date matching the selected weekday. Existing weeks are retained; overlapping weeks are rejected.</p><label className="hmi-field">Target tonnes<input type="number" min="0.001" max="1000000" step="0.001" required value={target} onChange={e=>setTarget(e.target.value)}/></label><label className="hmi-field">Target notes (optional)<textarea maxLength={500} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button className="hmi-primary-button">{busy?'Saving...':'Save weekly target'}</button></fieldset>{message&&<p role="status">{message}</p>}
 </form>
}
export function WeeklyTargets(){
 const [params]=useSearchParams();const [week,setWeek]=useState(params.get('week')??'')
 const report=useProtectedData((token,signal)=>getLive(token,week||null,signal),`target:${week}`)
 return <section className="linetech-screen"><Link to="/management">Back to Management</Link><h1>Weekly targets</h1><p>Set confirmed production targets for this factory. Production tonnes are not dispatch tonnes.</p><label className="hmi-field">View week starting<input type="date" value={week||report.data?.weekly.week_start||''} onChange={e=>setWeek(e.target.value)}/></label>{report.error&&<p role="alert">{report.error}</p>}{report.data?<TargetForm key={report.data.weekly.week_start} weekly={report.data.weekly} onSaved={()=>{}}/>:<p>Loading weekly target...</p>}<Link to="/dashboard">Open Live Operations</Link></section>
}
