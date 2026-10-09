import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../../api/client'
import { useManagementSession } from './session/useManagementSession'
import type { LineTechConfig, MachineGroup } from '../hmi/linetech'
import '../hmi/linetech.css'

interface Machine { id:number;name:string;active:boolean;display_order?:number;buttons:{id:number;name:string;active:boolean;event_type:string;display_order?:number}[] }
interface Setup { config:LineTechConfig;machines:Machine[] }
const split=(text:string)=>text.split('\n').map(s=>s.trim()).filter(Boolean)
function move<T>(items:T[],index:number,direction:number){const result=[...items];const next=index+direction;if(next>=0&&next<items.length)[result[index],result[next]]=[result[next],result[index]];return result}

export function LineTechSetup(){
 const {session,handleAuthError}=useManagementSession()
 const [lines,setLines]=useState<{id:number;name:string}[]>([]);const [line,setLine]=useState('')
 const [data,setData]=useState<Setup|null>(null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('')
 const [version,setVersion]=useState(0)
 useEffect(()=>{if(!session)return;const c=new AbortController();apiClient.get<{items:{id:number;name:string}[]}>('/api/v1/management/lines',{token:session.token,signal:c.signal}).then(r=>{setLines(r.items);setLine(current=>current||r.items[0]?.name||'')}).catch(e=>{if(!c.signal.aborted&&!handleAuthError(e))setMessage('Could not load lines.')});return()=>c.abort()},[session,handleAuthError])
 useEffect(()=>{if(!session||!line)return;const c=new AbortController();setData(null);apiClient.get<Setup>(`/api/v1/management/lines/${encodeURIComponent(line)}/linetech`,{token:session.token,signal:c.signal}).then(setData).catch(e=>{if(!c.signal.aborted&&!handleAuthError(e))setMessage('Could not load setup.')});return()=>c.abort()},[session,line,version,handleAuthError])
 function config(change:Partial<LineTechConfig>){if(data)setData({...data,config:{...data.config,...change}})}
 function group(index:number,value:MachineGroup){if(data)config({groups:data.config.groups.map((g,i)=>i===index?value:g)})}

 async function catalogue(path:string,body:unknown,patch=false){if(!session||busy)return;if(body && typeof body==="object" && "name" in body){body.name=String(body.name).trim();if(!body.name){setMessage("Enter a name before saving.");return}}setBusy(true);try{await (patch?apiClient.patch:apiClient.post)(`/api/v1/management/${path}`,body,{token:session.token});setVersion(v=>v+1);setMessage('Catalogue updated. Review navigation assignments before enabling LineTech.')}catch(e){if(!handleAuthError(e))setMessage(e instanceof Error?e.message:'Could not save.')}finally{setBusy(false)}}
 return <section className="linetech-screen"><Link to="/management">Back to Management</Link><h1>LineTech setup</h1><p>Configure the choices operators tap. Saved reports retain their original machine and fault identities.</p>
  <label className="hmi-field">Production line<select value={line} disabled={busy} onChange={e=>setLine(e.target.value)}>{lines.map(l=><option key={l.id}>{l.name}</option>)}</select></label>
  {message&&<p role="status">{message}</p>}
  {data&&<fieldset disabled={busy} className="linetech-choices"><legend>Configuration for {line}</legend>
   <label className="linetech-check"><input type="checkbox" checked={data.config.enabled} onChange={e=>config({enabled:e.target.checked})}/>Enable LineTech navigation on this line</label>
   <h2>Changeover choices</h2><p>One choice per line. Pack sizes are kilograms. Format and Size always request Engineering.</p>
   <div className="hmi-button-grid">{(['products','formats','sizes'] as const).map(key=><label className="hmi-field" key={key}>{key==='sizes'?'Pack sizes (kg)':key[0].toUpperCase()+key.slice(1)}<textarea rows={5} value={data.config[key].join('\n')} onChange={e=>config({[key]:e.target.value.split('\n')})}/></label>)}</div>
   <label className="linetech-check"><input type="checkbox" checked={data.config.product_engineering_required} onChange={e=>config({product_engineering_required:e.target.checked})}/>Product changes also require Engineering</label>
   <h2>Planned stops</h2>{data.config.planned.map((p,i)=><div className="linetech-confirm" key={i}><label className="hmi-field">Reason<input value={p.reason} onChange={e=>config({planned:data.config.planned.map((v,j)=>j===i?{...v,reason:e.target.value}:v)})}/></label><label className="hmi-field">Components (one per line)<textarea value={p.components.join('\n')} onChange={e=>config({planned:data.config.planned.map((v,j)=>j===i?{...v,components:e.target.value.split('\n')}:v)})}/></label><label className="linetech-check"><input type="checkbox" checked={p.active} onChange={e=>config({planned:data.config.planned.map((v,j)=>j===i?{...v,active:e.target.checked}:v)})}/>Active</label><button type="button" onClick={()=>config({planned:move(data.config.planned,i,-1)})}>Move up</button></div>)}
   <button type="button" className="hmi-secondary-button" onClick={()=>config({planned:[...data.config.planned,{reason:'New planned stop',components:[],active:true}]})}>Add planned stop</button>
   <h2>Machine navigation and categories</h2><p>Assign existing machines and fault buttons below. Disable a category or component to remove it from the HMI without deleting history.</p>
   {data.config.groups.map((g,gi)=><details key={g.key} className="linetech-confirm"><summary>{g.label}</summary><label className="hmi-field">Display name<input value={g.label} onChange={e=>group(gi,{...g,label:e.target.value})}/></label>
    {g.equipment.map((equipment,ei)=>{const machine=data.machines.find(m=>m.id===equipment.machine_id);const update=(change:Partial<typeof equipment>)=>group(gi,{...g,equipment:g.equipment.map((v,j)=>j===ei?{...v,...change}:v)});return <div key={equipment.machine_id} className="linetech-confirm"><h3>{machine?.name}</h3><label className="hmi-field">Component display name<input value={equipment.label} onChange={e=>update({label:e.target.value})}/></label><label className="linetech-check"><input type="checkbox" checked={equipment.active} onChange={e=>update({active:e.target.checked})}/>Show component</label><button onClick={()=>group(gi,{...g,equipment:move(g.equipment,ei,-1)})}>Move component up</button>
     {equipment.categories.map((category,ci)=>{const updateCategory=(change:Partial<typeof category>)=>update({categories:equipment.categories.map((v,j)=>j===ci?{...v,...change}:v)});return <div className="linetech-confirm" key={ci}><label className="hmi-field">Category name<input value={category.name} onChange={e=>updateCategory({name:e.target.value})}/></label><label className="linetech-check"><input type="checkbox" checked={category.active} onChange={e=>updateCategory({active:e.target.checked})}/>Show category</label><button onClick={()=>update({categories:move(equipment.categories,ci,-1)})}>Move category up</button>
      {machine?.buttons.filter(b=>b.event_type==='unplanned_fault').map(b=><label className="linetech-check" key={b.id}><input type="checkbox" checked={category.button_ids.includes(b.id)} onChange={e=>updateCategory({button_ids:e.target.checked?[...category.button_ids,b.id]:category.button_ids.filter(id=>id!==b.id)})}/>{b.name}{!b.active?' (disabled)':''}</label>)}</div>})}
     <button className="hmi-secondary-button" onClick={()=>update({categories:[...equipment.categories,{name:'New category',active:true,button_ids:[]}]})}>Add category</button></div>})}
    <label className="hmi-field">Add existing machine to group<select value="" onChange={e=>{const m=data.machines.find(m=>m.id===Number(e.target.value));if(m)group(gi,{...g,equipment:[...g.equipment,{machine_id:m.id,label:m.name,active:true,categories:[{name:'Faults',active:true,button_ids:[]}]}]})}}><option value="">Select machine</option>{data.machines.filter(m=>!data.config.groups.some(group=>group.equipment.some(e=>e.machine_id===m.id))).map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
   </details>)}
   <button className="hmi-primary-button" onClick={()=>{const cleaned={...data.config,products:split(data.config.products.join('\n')),formats:split(data.config.formats.join('\n')),sizes:split(data.config.sizes.join('\n')),planned:data.config.planned.map(p=>({...p,components:split(p.components.join('\n'))}))};setData({...data,config:cleaned});void saveClean(cleaned)}}>Save LineTech configuration</button>
   <details className="linetech-confirm"><summary>Manage machines and fault catalogue</summary><p>Save navigation changes above before editing the catalogue.</p>
    {data.machines.map(m=><details key={m.id}><summary>{m.name}</summary><form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void catalogue(`machines/${m.id}`,{name:f.get('name'),active:f.get('active')==='on',display_order:Number(f.get('order'))},true)}}><label className="hmi-field">Machine name<input name="name" defaultValue={m.name} required/></label><label>Order<input name="order" type="number" defaultValue={m.display_order??0}/></label><label className="linetech-check"><input name="active" type="checkbox" defaultChecked={m.active}/>Active</label><button>Save machine</button></form>
     {m.buttons.map((b,i)=><form key={b.id} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void catalogue(`buttons/${b.id}`,{name:f.get('name'),active:f.get('active')==='on',display_order:Number(f.get('order'))},true)}}><label className="hmi-field">Fault name<input name="name" defaultValue={b.name} required/></label><label>Order<input name="order" type="number" defaultValue={b.display_order??i}/></label><label className="linetech-check"><input name="active" type="checkbox" defaultChecked={b.active}/>Active</label><button>Save fault</button></form>)}
     <form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void catalogue(`machines/${m.id}/buttons`,{name:f.get('name'),event_type:'unplanned_fault',ownership:'Production'})}}><label className="hmi-field">New fault name<input name="name" required maxLength={120}/></label><button>Add fault</button></form>
    </details>)}
    <form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void catalogue(`lines/${lines.find(l=>l.name===line)?.id}/machines`,{name:f.get('name')})}}><label className="hmi-field">New machine name<input name="name" required maxLength={120}/></label><button>Add machine</button></form>
   </details>
  </fieldset>}
 </section>
 async function saveClean(cleaned:LineTechConfig){
  // Use the cleaned snapshot, not an asynchronous React state update.
  if(!session||busy)return;setBusy(true);try{await apiClient.post(`/api/v1/management/lines/${encodeURIComponent(line)}/linetech`,cleaned,{token:session.token,idempotencyKey:crypto.randomUUID()});setMessage('LineTech configuration saved. Refresh the HMI to load it.')}catch(e){if(!handleAuthError(e))setMessage(e instanceof Error?e.message:'Could not save.')}finally{setBusy(false)}
 }
}
