import type { CasepackerRequest } from './casepackerApi'

/** Sum accepted work intervals; waiting after a handover is not Engineering work. */
export function engineeringWorkMinutes(job: CasepackerRequest, now: number): number | null {
 let accepted: number | null = null
 let minutes = 0
 let started = false
 const end = job.cancelled_at ? Date.parse(job.cancelled_at) : now
 for (const update of [...job.updates].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at)||a.id-b.id)) {
  const at = Math.min(Date.parse(update.created_at), end)
  if(update.action === 'accept'){accepted=at;started=true}
  else if((update.action==='handover'||update.action==='ready') && accepted!==null){minutes+=Math.max(0,at-accepted)/60000;accepted=null}
 }
 if(accepted!==null)minutes+=Math.max(0,end-accepted)/60000
 if(!started && job.accepted_at)return Math.max(0,Math.min(job.ready_at?Date.parse(job.ready_at):now,end)-Date.parse(job.accepted_at))/60000
 return started ? minutes : null
}
