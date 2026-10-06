import { useEffect, useMemo, useState } from 'react'
import type { HourlyUpdateResponse, RunStateRun } from '../types'
import { buildShareSummary, renderSummaryImage, summaryText } from './hourlyShare'
import './hourly-share.css'

export function HourlyShareCard({run,result}:{run:RunStateRun;result:HourlyUpdateResponse}) {
 const [notes,setNotes]=useState('')
 const [message,setMessage]=useState('')
 const [busy,setBusy]=useState(false)
 const summary=useMemo(()=>buildShareSummary(run,result,notes),[run,result,notes])
 const [image,setImage]=useState<{summary:typeof summary;url:string;file:File}|null>(null)
 useEffect(()=>{
  let active=true;let url:string|undefined
  const timer=setTimeout(()=>{
   renderSummaryImage(summary).then(blob=>{
    if(!active)return
    url=URL.createObjectURL(blob)
    setImage({summary,url,file:new File([blob],`pulse-run-${result.production_run_id}-hour-${result.hourly_update_id}.png`,{type:'image/png'})})
   }).catch(()=>{if(active)setMessage('Image export is unavailable here. Take a screenshot of the summary card below.')})
  },250)
  return()=>{active=false;clearTimeout(timer);if(url)URL.revokeObjectURL(url)}
 },[summary,result.production_run_id,result.hourly_update_id])
 const ready=image?.summary===summary?image:null
 async function share(){
  if(!ready||busy)return
  setBusy(true);setMessage('')
  try {
   if(navigator.canShare?.({files:[ready.file]}) && navigator.share){
    await navigator.share({files:[ready.file],title:'Production update'})
   }else{setMessage('Download the PNG below, then attach it in WhatsApp. You can also screenshot the summary card.')}
  }catch(error){
   if(!(error instanceof Error && error.name==='AbortError'))setMessage('Sharing was unavailable. Download the PNG and attach it in WhatsApp.')
  }finally{setBusy(false)}
 }
 return <section className="hourly-share" aria-label="Share saved hourly update">
  <h2>Share this hour</h2>
  <p>Your reading is saved. Add optional handover notes, then share the image and choose WhatsApp. Review the card before sending.</p>
  <label className="hmi-field">Notes for the share card (optional)
   <textarea value={notes} onChange={e=>setNotes(e.target.value)} maxLength={1500} rows={4} placeholder="Checks, film or label changes, issues, actions and what to monitor..."/>
  </label>
  <p className="hmi-field-help">These notes are for this image only. Record faults, quality concerns and actions in their normal workflows too. Notes are not retained when you leave this screen.</p>
  <div className="hourly-share__actions">
   <button type="button" className="hmi-primary-button" disabled={!ready||busy} onClick={()=>void share()}>{busy?'Opening share...':'Share image'}</button>
   {ready&&<a className="pulse-button hourly-share__download" href={ready.url} download={ready.file.name}>Download PNG</a>}
  </div>
  {message&&<p role="status">{message}</p>}
  <article className="hourly-share__card" aria-label="Screenshot-ready production summary">
   <p className="hourly-share__brand">TONNAGE FLOW / PULSE</p>
   <h3>{summary.title}</h3><p>{summary.period}</p><p>{summary.identity}</p><p>{summary.product}</p>
   <dl className="hourly-share__metrics">{summary.metrics.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
   {summary.context.map((line,index)=><p key={index}>{line}</p>)}
   {summary.notes&&<div className="hourly-share__notes"><h4>Technician share notes</h4><small>Not saved to production history</small><p>{summary.notes}</p></div>}
   <footer>Saved production reading | Tonnage Flow Pulse</footer>
  </article>
  {ready&&<details><summary>Open generated image for saving or screenshot</summary><img className="hourly-share__image" src={ready.url} alt={summaryText(summary)}/></details>}
 </section>
}
