import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { HourlyShareCard } from './HourlyShareCard'
import { buildShareSummary, outputGauge, oeeGauge, renderSummaryImage } from './hourlyShare'
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
 expect(summary.context.join(' ')).toContain('Awaiting data')
 expect(summary.achievement).toBe(84.62)
 expect(summary.identity).not.toMatch(/Run #|Reading #/)
 expect(summary.target).toBe(7800)
 expect(summary.actual).toBe(6600)
 expect(summary.oee).toContainEqual(['Estimated OEE','Unavailable'])
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

it('preserves output above target and flags review instead of presenting it as OEE',()=>{
 const summary=buildShareSummary(runState().run,{...result,actual_packs:11000,expected_packs:3246.52,production_achievement_percent:338.8},'')
 expect(summary.achievement).toBe(338.8)
 expect(summary.context.join(' ')).toContain('Over target')
 expect(summary.oeeReason).toContain('Awaiting downtime data')
})

it.each([[0,'#ef5350'],[44.9,'#ef5350'],[45,'#ffa726'],[59.9,'#ffa726'],[60,'#ffa726'],[64.9,'#ffa726'],[65,'#2dd477'],[100,'#2dd477']])('colours %s percent at the correct threshold', (value,color)=>{
 expect(outputGauge(value).color).toBe(color)
})
it('keeps above-target numbers visible while bounding the ring, and treats missing data separately from zero',()=>{
 expect(outputGauge(338.8)).toMatchObject({fill:100,label:'338.8%'})
 expect(outputGauge(null)).toMatchObject({fill:0,label:'N/A',color:'#71857b'})
 expect(outputGauge(0).label).toBe('0.0%')
})

it('failed sample flags concern without altering quality or the OEE calculation',()=>{
 const r={...result,estimated_oee:{availability_percent:100,performance_percent:100,estimated_quality_percent:98,estimated_oee_percent:98,unavailable_reason:null,quality_basis:'provisional'}}
 const passed=buildShareSummary(runState().run,r,'','passed')
 const failed=buildShareSummary(runState().run,r,'','concern')
 expect(passed.sample).toBe('Sample check: Passed')
 expect(failed.sample).toBe('Quality concern - review required')
 expect(failed.oee).toEqual(passed.oee)
 expect(failed.oee).toContainEqual(['Quality','98.0% (provisional)'])
})

it.each([[44.9,'Low','#ef5350'],[45,'Moderate','#ffa726'],[64.9,'Moderate','#ffa726'],[65,'Good','#2dd477'],[98,'Good','#2dd477']])('uses OEE bands at %s', (value,status,color)=>{
 expect(oeeGauge(value as number)).toMatchObject({status,color})
})
it('shows conflicting OEE as a review state without hiding the calculated value',()=>{
 expect(oeeGauge(332)).toMatchObject({label:'332.0%',fill:0,status:'Review required',color:'#ffa726'})
 expect(oeeGauge(80,true).status).toBe('Review required')
 expect(oeeGauge(null)).toMatchObject({label:'N/A',status:'Awaiting data',fill:0})
})
it('uses produced divided by expected for the primary ring',async()=>{
 const r={...result,production_achievement_percent:50,estimated_oee:{availability_percent:100,performance_percent:100,estimated_quality_percent:98,estimated_oee_percent:98,unavailable_reason:null}}
 render(<HourlyShareCard run={runState().run} result={r}/>)
 expect(screen.getByRole('img',{name:/Output vs Target: 50.0%. Moderate/})).toBeInTheDocument()
 await screen.findByRole('link',{name:'Download PNG'})
})
