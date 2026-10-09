import { useEffect, useState } from 'react'
import { apiClient } from '../../../api/client'
import type { ChangeoverSelection, LineTechConfig } from '../linetech'

export function LineTechChangeoverScreen({line,isSubmitting,errorMessage,onConfirm,onBack}: {
 line:string;isSubmitting:boolean;errorMessage:string|null;onConfirm:(selection:ChangeoverSelection)=>void;onBack:()=>void;
}) {
 const [data,setData]=useState<{config:LineTechConfig;previous:{product:string;format:string;pack_weight_kg:number}|null}|null>(null)
 const [error,setError]=useState('');const [kind,setKind]=useState<ChangeoverSelection['kind']|null>(null)
 const [next,setNext]=useState('')
 useEffect(()=>{const c=new AbortController();apiClient.get<NonNullable<typeof data>>(`/api/v1/lines/${encodeURIComponent(line)}/changeover-options`,{signal:c.signal}).then(setData).catch(()=>{if(!c.signal.aborted)setError('Could not load configured choices. Go back and retry.')});return()=>c.abort()},[line])
 const choices=kind && data ? data.config[kind==='product'?'products':kind==='format'?'formats':'sizes'] : []
 const current=kind && data?.previous ? String(data.previous[kind==='product'?'product':kind==='format'?'format':'pack_weight_kg']) : ''
 return <div className="hmi-screen linetech-screen"><p className="linetech-eyebrow">CHANGEOVER · {line}</p><h1>{!kind?'What is changing?':`${kind[0].toUpperCase()+kind.slice(1)} changeover`}</h1>
  {data?.previous && <p>Current: {data.previous.product} · {data.previous.pack_weight_kg} kg · {data.previous.format}</p>}
  <div className="hmi-button-grid">{!kind ? (['product','format','size'] as const).map(k=><button className="linetech-tile linetech-changeover" key={k} disabled={!data || isSubmitting} onClick={()=>setKind(k)}>{k[0].toUpperCase()+k.slice(1)}</button>)
   : choices.map(value=><button className="linetech-tile" key={value} aria-pressed={next===value} disabled={isSubmitting || value===current} onClick={()=>setNext(value)}>{value}{kind==='size'?' kg':''}</button>)}</div>
  {kind && !choices.length && data && <p role="status">Management must configure the available {kind} choices before this changeover can start.</p>}
  {next && <div className="linetech-confirm"><h2>{current} → {next}{kind==='size'?' kg':''}</h2><p>{kind!=='product'||data?.config.product_engineering_required?'Engineering will receive one linked job.':'No Engineering job required by this line configuration.'} The production stop continues until the next run starts.</p><button className="hmi-primary-button" disabled={isSubmitting} onClick={()=>kind && onConfirm({kind,next_value:next})}>Confirm Changeover</button></div>}
  {(error||errorMessage)&&<p role="alert">{error||errorMessage}</p>}
  <button className="hmi-secondary-button" disabled={isSubmitting} onClick={()=>{if(kind){setKind(null);setNext('')}else onBack()}}>Back</button>
 </div>
}
