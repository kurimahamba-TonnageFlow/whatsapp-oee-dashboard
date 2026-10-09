import { fireEvent,render,screen,waitFor } from '@testing-library/react'
import { beforeEach,expect,it,vi } from 'vitest'
import { LineTechStoppageScreen } from './LineTechStoppageScreen'
import { apiClient } from '../../../api/client'
import { getCasepackerStatus } from '../../engineering/casepackerApi'

vi.mock('../../../api/client',async original=>({...await original<typeof import('../../../api/client')>(),apiClient:{get:vi.fn(),post:vi.fn()}}))
vi.mock('../../engineering/casepackerApi',()=>({getCasepackerStatus:vi.fn()}))
const context={changeover:{workflow:{kind:'product',next_value:'Brown Basmati',previous_value:'White Basmati',engineering_required:false,qa_status:'awaiting_verification',verification:null,cancelled_at:null},physical_ended_at:'2026-10-09T08:10:00Z',restarted_at:null}}
function props(){return {stoppage:{stoppageId:7,productionLine:'Rovema',kind:'changeover' as const,reason:null,startedAt:'2026-10-09T08:00:00Z',startedBy:'Liam',endedAt:null,durationMinutes:null},isSubmitting:false,errorMessage:null,onEnd:vi.fn(),onStartNewRun:vi.fn(),onHome:vi.fn()}}
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();vi.mocked(apiClient.get).mockResolvedValue(context);vi.mocked(getCasepackerStatus).mockResolvedValue({request:null})})
it('does not permit restart just because physical work is complete',async()=>{
 const input=props();render(<LineTechStoppageScreen {...input}/>);await screen.findByText('Record verification')
 expect(screen.queryByRole('button',{name:'Enter New Run Details'})).not.toBeInTheDocument()
 expect(screen.getByRole('button',{name:'Save verification'})).toBeDisabled()
 expect(input.onStartNewRun).not.toHaveBeenCalled()
})
it('replays the original verification after remount without changing its key or evidence',async()=>{
 vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('Reply lost')).mockResolvedValueOnce({status:'success'})
 const first=render(<LineTechStoppageScreen {...props()}/>);await screen.findByText('Record verification')
 for(const label of ['First-off approved','Label checked','Date code checked','CCP check passed'])fireEvent.click(screen.getByLabelText(label))
 fireEvent.change(screen.getByLabelText('QA record reference'),{target:{value:'QA-001'}})
 fireEvent.click(screen.getByRole('button',{name:'Save verification'}))
 await screen.findByText('Reply lost');const original=vi.mocked(apiClient.post).mock.calls[0]
 first.unmount();render(<LineTechStoppageScreen {...props()}/>);await screen.findByText('Record verification');fireEvent.click(await screen.findByRole('button',{name:'Retry original action'}))
 await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(2))
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Retry original action'})).not.toBeInTheDocument())
 expect(vi.mocked(apiClient.post).mock.calls[1]).toEqual(original)
 expect(JSON.parse(String(original[1]&&JSON.stringify(original[1]))).reference).toBe('QA-001')
})
