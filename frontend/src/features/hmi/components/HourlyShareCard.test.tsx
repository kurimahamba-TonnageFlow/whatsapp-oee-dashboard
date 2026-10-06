import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { HourlyShareCard } from './HourlyShareCard'
import { buildShareSummary, renderSummaryImage } from './hourlyShare'
import { runState } from '../hmiTestState'
import type { HourlyUpdateResponse } from '../types'
vi.mock('./hourlyShare',async importOriginal=>({...await importOriginal<typeof import('./hourlyShare')>(),renderSummaryImage:vi.fn()}))
const result:HourlyUpdateResponse={status:'success',hourly_update_id:77,production_run_id:99,production_line:'Rovema',hour_start:'2026-10-05T23:00:00Z',hour_label:'00:00?01:00',shift:'Nights',period_started_at:'2026-10-05T23:00:00Z',period_ended_at:'2026-10-06T00:00:00Z',period_minutes:60,pallets_produced:6,expected_packs:7800,expected_pallets:7.8,expected_tonnes:7.8,actual_packs:6600,actual_tonnes:6.6,output_gap_packs:1200,production_achievement_percent:84.62,planned_downtime_minutes:2,pallets_remaining:10,total_pallets_completed:20,potential_overrun_pallets:2,loss_review:{target_packs:7800,remaining_gap_packs:940,equivalent_minutes:7.23,prompt_required:false}}
beforeEach(()=>{vi.mocked(renderSummaryImage).mockResolvedValue(new Blob(['png'],{type:'image/png'}));vi.stubGlobal('URL',class extends URL {static createObjectURL=vi.fn(()=> 'blob:summary');static revokeObjectURL=vi.fn()})})
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})
it('keeps hourly and cumulative output distinct, uses UK midnight and retains unaccounted gap',()=>{
 const summary=buildShareSummary(runState().run,result,'Monitoring sealing unit')
 expect(summary.metrics).toContainEqual(['Pallets this hour','6'])
 expect(summary.metrics).toContainEqual(['Pallets this run','22'])
 expect(summary.period).toContain('06 Oct 2026')
 expect(summary.context.join(' ')).toContain('940 packs')
 expect(summary.metrics).toContainEqual(['Output vs target (not OEE)','84.62%'])
})
it('shares a ready PNG file through the native share sheet',async()=>{
 const share=vi.fn().mockResolvedValue(undefined)
 Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>true})
 Object.defineProperty(navigator,'share',{configurable:true,value:share})
 render(<HourlyShareCard run={runState().run} result={result}/>)
 await screen.findByRole('link',{name:'Download PNG'})
 fireEvent.click(screen.getByRole('button',{name:'Share image'}))
 await waitFor(()=>expect(share).toHaveBeenCalled())
 expect(share.mock.calls[0][0].files[0].type).toBe('image/png')
})
it('keeps download available when native file sharing is unsupported',async()=>{
 Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>false})
 render(<HourlyShareCard run={runState().run} result={result}/>)
 await screen.findByRole('link',{name:'Download PNG'})
 fireEvent.click(screen.getByRole('button',{name:'Share image'}))
 await screen.findByText(/Download the PNG below/)
 fireEvent.change(screen.getByLabelText('Notes for the share card (optional)'),{target:{value:'Film changed. Monitoring splice.'}})
 expect(screen.getByRole('button',{name:'Share image'})).toBeDisabled()
 await waitFor(()=>expect(screen.getByRole('button',{name:'Share image'})).toBeEnabled())
 expect(screen.getByRole('article')).toHaveTextContent('Film changed. Monitoring splice.')
})
it('retains a screenshot card if canvas export fails',async()=>{
 vi.mocked(renderSummaryImage).mockRejectedValue(new Error('canvas unavailable'))
 render(<HourlyShareCard run={runState().run} result={result}/>)
 await screen.findByText(/Image export is unavailable here/)
 expect(screen.getByRole('article',{name:'Screenshot-ready production summary'})).toBeInTheDocument()
})
