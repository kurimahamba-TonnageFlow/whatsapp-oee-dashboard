import { useEffect, useMemo, useState } from 'react'
import type { HourlyUpdateResponse, RunStateRun } from '../types'
import { buildShareSummary, outputGauge, renderSummaryImage, summaryText, type SampleCheck } from './hourlyShare'
import './hourly-share.css'

export function HourlyShareCard({run,result}:{run:RunStateRun;result:HourlyUpdateResponse}) {
 const [notes,setNotes]=useState('')
 const [sample,setSample]=useState<SampleCheck>('not-recorded')
 const [message,setMessage]=useState('')
 const [busy,setBusy]=useState(false)
 const summary=useMemo(()=>buildShareSummary(run,result,notes,sample),[run,result,notes,sample])
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
 const gauge={...outputGauge(summary.achievement),review:false,status:summary.achievement==null?'Awaiting data':summary.achievement>100?'Over target - review figures':summary.achievement<45?'Low':summary.achievement<65?'Moderate':'Good'}
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
  <label className="hmi-field">Hourly sample check (share card only)
   <select value={sample} onChange={e=>setSample(e.target.value as SampleCheck)}>
    <option value="not-recorded">Not recorded</option><option value="passed">Passed</option><option value="concern">Quality concern</option>
   </select>
  </label>
  <div className="hourly-share__actions">
   <button type="button" className="hmi-primary-button" disabled={!ready||busy} onClick={()=>void share()}>{busy?'Opening share...':'Share image'}</button>
   {ready&&<a className="pulse-button hourly-share__download" href={ready.url} download={ready.file.name}>Download PNG</a>}
  </div>
  {message&&<p role="status">{message}</p>}
  <article className="hourly-share__card" aria-label="Screenshot-ready production summary">
   <p className="hourly-share__brand">TONNAGE FLOW / PULSE</p>
   <h3>{summary.title}</h3><p>{summary.period}</p><p>{summary.identity}</p><p>{summary.product}</p>
   <dl className="hourly-share__metrics">{summary.metrics.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
   <section className="hourly-share__chart" aria-label="Output vs Target infographic">
    <h4>Output vs Target</h4>
    <div className="hourly-share__gauge" role="img" aria-label={`Output vs Target: ${gauge.label}. ${gauge.status}. Trial bands: red below 45%, amber below 65%, green up to 100%.`}>
     <svg viewBox="0 0 240 240" aria-hidden="true">
      <circle cx="120" cy="120" r="98" fill="none" stroke={gauge.review?gauge.color:"#30443b"} strokeDasharray={gauge.review?"8 6":undefined} strokeWidth="22"/>
      <circle cx="120" cy="120" r="98" fill="none" stroke={gauge.color} strokeWidth="22" pathLength="100" strokeDasharray={`${gauge.fill} 100`} transform="rotate(-90 120 120)"/>
      <text x="120" y="117" textAnchor="middle" fill="white" fontSize="32" fontWeight="700">{gauge.label}</text>
      <text x="120" y="145" textAnchor="middle" fill="#d5dedb" fontSize="15">Output vs Target</text>
     </svg>
    </div>
    <p className="hourly-share__gauge-status" style={{color:gauge.color}}>{gauge.status}</p>
    <p className="hourly-share__legend">Trial bands: red &lt;45% | amber 45-&lt;65% | green 65-100%</p>
    <p className="hourly-share__attainment">Output vs Target <strong>{outputGauge(summary.achievement).label}</strong>{summary.achievement!=null&&summary.achievement>100?' - over target':''}</p>
    <dl className="hourly-share__production">
     <div><dt>Expected production</dt><dd>{Math.round(summary.target).toLocaleString('en-GB')} packs</dd></div>
     <div><dt>Actual production</dt><dd>{Math.round(summary.actual).toLocaleString('en-GB')} packs</dd></div>
     <div><dt>Production shortfall</dt><dd>{Math.round(summary.shortfall).toLocaleString('en-GB')} packs</dd></div>
    </dl>
   </section>
   {summary.sample&&<p className="hourly-share__sample">{summary.sample} <small>(technician confirmation for this card)</small></p>}
   {summary.context.map((line,index)=><p key={index}>{line}</p>)}
   {summary.notes&&<div className="hourly-share__notes"><h4>Technician share notes</h4><small>Not saved to production history</small><p>{summary.notes}</p></div>}
   <footer>Saved production reading | Tonnage Flow Pulse</footer>
  </article>
  {ready&&<details><summary>Open generated image for saving or screenshot</summary><img className="hourly-share__image" src={ready.url} alt={summaryText(summary)}/></details>}
 </section>
}
