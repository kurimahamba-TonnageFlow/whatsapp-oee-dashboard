import type { HourlyUpdateResponse, RunStateRun } from '../types'

export interface ShareSummary { title: string; period: string; identity: string; product: string; metrics: [string, string][]; context: string[]; notes: string }
const number = (value: number) => value.toLocaleString('en-GB', { maximumFractionDigits: 2 })
const dateTime = (value: string) => new Date(value).toLocaleString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
export function buildShareSummary(run: RunStateRun, result: HourlyUpdateResponse, notes: string): ShareSummary {
 const context = (result.loss_review?.operating_context ?? []).filter(r => !r.superseded).map(r =>
  `Reported setting: ${number(r.speed_ppm)} packs/min from ${dateTime(r.effective_at)}. ${r.changed_by ?? 'Reporter not recorded'}${r.reason ? ` - ${r.reason}` : ''}. Context only.`)
 if (result.loss_review?.remaining_gap_packs != null) context.push(`Unaccounted output gap: ${number(result.loss_review.remaining_gap_packs)} packs. Not measured downtime.`)
 context.push(...(result.loss_review?.limitations ?? []))
 return {
  title: `${result.production_line} | Production update`,
  period: `${dateTime(result.period_started_at)} to ${dateTime(result.period_ended_at)} (UK time)`,
  identity: `${run.line_technician} | ${result.shift} | Run #${result.production_run_id} / Reading #${result.hourly_update_id}`,
  product: `${run.customer} | ${run.product} | ${run.format ?? `${run.pack_weight_kg} kg x ${run.packs_per_case}`}`,
  metrics: [['Pallets this hour', number(result.pallets_produced)], ['Pallets this run', number(result.total_pallets_completed + result.potential_overrun_pallets)],
   ['Actual packs', number(result.actual_packs)], ['Saved target packs', number(result.expected_packs)],
   ['Output vs target (not OEE)', result.production_achievement_percent == null ? 'Not available' : `${number(result.production_achievement_percent)}%`],
   ['Period covered', `${number(result.period_minutes)} min`]],
  context, notes: notes.trim(),
 }
}
export function summaryText(summary: ShareSummary) {
 return [summary.title, summary.period, summary.identity, summary.product, ...summary.metrics.map(([k,v])=>`${k}: ${v}`), ...summary.context,
  summary.notes ? `Technician share notes (not saved to production history):\n${summary.notes}` : '', 'Tonnage Flow Pulse | Saved production reading'].filter(Boolean).join('\n')
}

/** Draw text directly: no third-party upload, DOM screenshot library or remote fonts. */
export async function renderSummaryImage(summary: ShareSummary): Promise<Blob> {
 const canvas=document.createElement('canvas'); canvas.width=1080
 const ctx=canvas.getContext('2d'); if(!ctx)throw new Error('Image creation is unavailable. Screenshot the card instead.')
 const commands: {text:string;x:number;y:number;size:number;color:string;bold:boolean}[]=[]
 let y=64
 function text(value:string,size=30,color='#d5dedb',bold=false,x=64,width=952) {
  ctx!.font=`${bold?'700':'400'} ${size}px Arial`
  for(const paragraph of value.split('\n')) {
   let line=''
   // Character wrapping also handles long machine identifiers without clipping.
   for(const char of paragraph) {
    if(ctx!.measureText(line+char).width>width && line){commands.push({text:line,x,y,size,color,bold});y+=size*1.4;line=''}
    line+=char
   }
   commands.push({text:line,x,y,size,color,bold});y+=size*1.4
  }
 }
 text('TONNAGE FLOW / PULSE',24,'#b7ed65',true);y+=24
 text(summary.title,46,'#ffffff',true);y+=10
 text(summary.period,26);text(summary.identity,25);y+=12;text(summary.product,30);y+=30
 for(const [label,value] of summary.metrics){text(label.toUpperCase(),22,'#b7ed65',true);text(value,44,'#ffffff',true);y+=14}
 for(const line of summary.context){text(line,27);y+=16}
 if(summary.notes){y+=14;text('TECHNICIAN SHARE NOTES',24,'#b7ed65',true);text('(Not saved to production history)',22);y+=10;text(summary.notes,30);y+=20}
 text('SAVED PRODUCTION READING | TONNAGE FLOW PULSE',21,'#a3b2ac')
 canvas.height=Math.ceil(y+50)
 ctx.textBaseline='top'
 ctx.fillStyle='#101d1b';ctx.fillRect(0,0,1080,canvas.height)
 ctx.fillStyle='#b7ed65';ctx.fillRect(0,0,1080,10)
 for(const command of commands){ctx.font=`${command.bold?'700':'400'} ${command.size}px Arial`;ctx.fillStyle=command.color;ctx.fillText(command.text,command.x,command.y)}
 return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Could not create the image. Screenshot the card instead.')),'image/png'))
}
