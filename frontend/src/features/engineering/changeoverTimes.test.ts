import { expect,it } from 'vitest'
import { engineeringWorkMinutes } from './changeoverTimes'
import type { CasepackerRequest } from './casepackerApi'
it('excludes handover waiting and freezes completed work',()=>{
 const job={accepted_at:'2026-10-09T10:30:00Z',ready_at:'2026-10-09T10:40:00Z',updates:[
  {id:1,action:'accept',created_at:'2026-10-09T10:00:00Z'},
  {id:2,action:'handover',created_at:'2026-10-09T10:10:00Z'},
  {id:3,action:'accept',created_at:'2026-10-09T10:30:00Z'},
  {id:4,action:'ready',created_at:'2026-10-09T10:40:00Z'},
 ]} as CasepackerRequest
 expect(engineeringWorkMinutes(job,Date.parse('2026-10-09T11:00:00Z'))).toBe(20)
})
