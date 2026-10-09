import type { HourlyUpdateResponse, RunStateRun } from '../types'

export type SampleCheck = 'not-recorded' | 'passed' | 'concern'
export interface ShareSummary {
 title: string; period: string; identity: string; product: string; achievement: number | null
 oeeValue: number | null; oeeReview: boolean; target: number; actual: number; shortfall: number; metrics: [string,string][]
 oee: [string,string][]; oeeReason: string; context: string[]; notes: string; sample: string
}
const whole = (value: number) => value.toLocaleString('en-GB', {maximumFractionDigits:0})
const decimal = (value: number) => value.toLocaleString('en-GB', {minimumFractionDigits:1,maximumFractionDigits:1})
const percent = (value: number | null | undefined) => value == null ? 'Unavailable' : `${decimal(value)}%`
const minutes = (value: number | null | undefined) => value == null ? 'Awaiting data' : `${decimal(value)} min`
const dateTime = (value: string) => new Date(value).toLocaleString('en-GB', {timeZone:'Europe/London', day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})
export function outputGauge(value: number | null) {
 const valid = value != null && Number.isFinite(value) && value >= 0
 return {fill:valid ? Math.min(value,100):0,
 color:!valid?'#71857b':value<45?'#ef5350':value<65?'#ffa726':'#2dd477',
 label:valid ? `${decimal(value)}%`:'N/A'}
}
export function oeeGauge(value: number | null, review=false) {
 const g=outputGauge(value)
 const missing=value==null||!Number.isFinite(value)
 const invalid=review||(!missing&&(value<0||value>100))
 return {...g, color:missing?'#71857b':invalid?'#ffa726':g.color,
  fill:missing||invalid?0:g.fill,
  status:missing?'Awaiting data':invalid?'Review required':value<45?'Low':value<65?'Moderate':'Good',
  review:invalid&&!missing}
}
export function buildShareSummary(run:RunStateRun,result:HourlyUpdateResponse,notes:string,sample:SampleCheck='not-recorded'):ShareSummary {
 const report=result.production_report, oee=result.estimated_oee
 const target=report?.target_packs ?? result.expected_packs, actual=report?.actual_packs ?? result.actual_packs
 const achievement=report ? report.attainment_percent : result.production_achievement_percent
 const context:string[]=[]
 if(achievement!=null && achievement>100)context.push('Over target - review speed, pallet conversion, counts and reporting period.')
 context.push(`Planned downtime: ${minutes(report?.planned_minutes)} | Unplanned downtime: ${minutes(report?.unplanned_minutes)}`)
 if(report?.excluded_minutes)context.push(`Excluded planned stops: ${minutes(report.excluded_minutes)}`)
 if(report?.reasons.length)context.push(`Recorded reasons: ${report.reasons.join('; ').replace(/\s+/g,' ').slice(0,300)}`)
 if(report?.unexplained_shortfall!=null && report.unexplained_shortfall>0)context.push(`Unexplained shortfall: ${whole(report.unexplained_shortfall)} packs. Speed loss, rejects or count errors may contribute.`)

 const quality=percent(oee?.estimated_quality_percent)+(oee?.estimated_quality_percent!=null ? (oee.quality_basis==='measured'?' (measured)':' (provisional)'):'')
 return {title:`${result.production_line} | Production update`,period:`${dateTime(result.period_started_at)} to ${dateTime(result.period_ended_at)} (UK time)`,identity:`${run.line_technician} | ${result.shift}`,
 product:`${run.customer} | ${run.product} | ${run.format??`${run.pack_weight_kg} kg x ${run.packs_per_case}`}`,
 oeeValue:oee?.estimated_oee_percent??null,
 oeeReview:sample==='concern'||(oee?.performance_percent??0)>100||(oee?.warnings?.length??0)>0,
 target,actual,achievement,shortfall:report?.shortfall_packs??result.output_gap_packs,
 metrics:[['Pallets this hour',result.pallets_produced.toLocaleString('en-GB', {maximumFractionDigits:4})],['Pallets this run',(result.total_pallets_completed+result.potential_overrun_pallets).toLocaleString('en-GB', {maximumFractionDigits:4})],['Period covered',minutes(report?.period_minutes??result.period_minutes)],['Standard speed',report?.standard_speed_ppm!=null?`${decimal(report.standard_speed_ppm)} packs/min`:'Unavailable']],
 oee:[['Availability',percent(oee?.availability_percent)],['Performance',percent(oee?.performance_percent)],['Quality',quality],['Estimated OEE',percent(oee?.estimated_oee_percent)]],
 oeeReason:[oee?.unavailable_reason,oee?.output_basis??'Awaiting downtime data',oee?.estimated_quality_percent!=null && oee.quality_basis!=='measured'?'Quality is a provisional assumption, not a measured result.':''].filter(Boolean).join(' '),
 context,notes:notes.trim(),sample:sample==='passed'?'Sample check: Passed':sample==='concern'?'Quality concern - review required':''}
}
export function summaryText(s:ShareSummary){return [s.title,s.period,s.identity,s.product,...s.metrics.map(([k,v])=>`${k}: ${v}`),`Output vs Target: ${outputGauge(s.achievement).label}`,`Expected production: ${whole(s.target)} packs`,`Actual production: ${whole(s.actual)} packs`,`Production shortfall: ${whole(s.shortfall)} packs`,s.sample,...s.context,s.notes].filter(Boolean).join('\n')}

/** Local canvas export; uses the same summary as the mobile card. */
export async function renderSummaryImage(s:ShareSummary):Promise<Blob>{
 const canvas=document.createElement('canvas');canvas.width=1080
 const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Image creation unavailable')
 const commands:{value:string,x:number,y:number,size:number,color:string,bold:boolean}[]=[]
 let y=42
 function text(value:string,size=28,color='#d5dedb',bold=false,x=44,width=992){
  ctx!.font=`${bold?'700':'400'} ${size}px Arial`
  for(const paragraph of value.split('\n')) {
   let line=''
   for(const word of paragraph.split(/\s+/)) {
    const next=line?`${line} ${word}`:word
    if(ctx!.measureText(next).width>width&&line){commands.push({value:line,x,y,size,color,bold});y+=size*1.3;line=''}
    if(ctx!.measureText(word).width>width){for(const char of word){if(ctx!.measureText(line+char).width>width){commands.push({value:line,x,y,size,color,bold});y+=size*1.3;line=''}line+=char}}
    else line=line?`${line} ${word}`:word
   }
   commands.push({value:line,x,y,size,color,bold});y+=size*1.3
  }
 }
 text('TONNAGE FLOW / PULSE',24,'#b7ed65',true);y+=12;text(s.title,40,'#fff',true);y+=8
 text(s.period,25);text(s.identity,28);text(s.product,28);y+=16
 for(let i=0;i<s.metrics.length;i+=2){const top=y;let bottom=y;for(let j=0;j<2&&i+j<s.metrics.length;j++){y=top;text(s.metrics[i+j][0],22,'#b7ed65',false,44+j*510,480);text(s.metrics[i+j][1],30,'#fff',true,44+j*510,480);bottom=Math.max(bottom,y)}y=bottom+10}
 text('OUTPUT VS TARGET',26,'#b7ed65',true)
 const ringY=y;y+=350
 const indicator={...outputGauge(s.achievement),status:s.achievement==null?'Awaiting data':s.achievement>100?'Over target - review figures':s.achievement<45?'Low':s.achievement<65?'Moderate':'Good'}
 text(`${indicator.status} | Trial bands: red <45%, amber 45-<65%, green 65-100%`,24,indicator.color,true)
 text(`Output vs Target: ${outputGauge(s.achievement).label}`,28,'#fff',true);y+=8
 text(`Expected production: ${whole(s.target)} packs`,30,'#fff',true)
 text(`Actual production: ${whole(s.actual)} packs`,30,'#fff',true)
 text(`Production shortfall: ${whole(s.shortfall)} packs`,30,'#fff',true);y+=22
 if(s.sample){text(s.sample,28,s.sample.includes('concern')?'#ffa726':'#b7ed65',true);y+=10}
 for(const line of s.context){text(line,26);y+=10}
 if(s.notes){text('Share notes (not saved to history)',22,'#b7ed65');text(s.notes,26);y+=10}
 text('SAVED PRODUCTION READING | TONNAGE FLOW PULSE',20,'#a3b2ac')
 canvas.height=Math.ceil(y+36);ctx.fillStyle='#101d1b';ctx.fillRect(0,0,1080,canvas.height);ctx.fillStyle='#b7ed65';ctx.fillRect(0,0,1080,7)
 const g={...outputGauge(s.achievement),review:false},cx=540,cy=ringY+157,r=132;ctx.lineWidth=24;ctx.strokeStyle=g.review?'#ffa726':'#30443b';ctx.setLineDash(g.review?[12,10]:[]);ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.stroke()
 ctx.setLineDash([]);if(g.fill>0){ctx.strokeStyle=g.color;ctx.beginPath();ctx.arc(cx,cy,r,-Math.PI/2,-Math.PI/2+2*Math.PI*g.fill/100);ctx.stroke()}
 ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#fff';ctx.font='700 60px Arial';ctx.fillText(g.label,cx,cy-10);ctx.font='23px Arial';ctx.fillText('Output vs Target',cx,cy+35)
 ctx.textAlign='left';ctx.textBaseline='top'
 for(const cmd of commands){ctx.font=`${cmd.bold?'700':'400'} ${cmd.size}px Arial`;ctx.fillStyle=cmd.color;ctx.fillText(cmd.value,cmd.x,cmd.y)}
 return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Could not create image')),'image/png'))
}
