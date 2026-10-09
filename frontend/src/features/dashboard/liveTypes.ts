import type { HourSlot } from './types'
export interface LiveWindow { start:string; end:string; start_local:string; end_local:string; label:string; timezone:string }
export interface LiveJob { run_id:number; product:string; customer:string; format:string|null; pack_weight_kg:number|null; speed_ppm:number|null; completed_pallets:number|null; remaining_pallets:number|null; progress_percent:number|null; estimate_hours:number|null; estimate_status:string }
export interface LiveChangeover {id:number;kind:string;elapsed_minutes:number;physical_complete:boolean;qa_status:string;engineering_ready:boolean;engineer:string|null}
export interface LiveLine {name:string;status:'running'|'stopped'|'changeover'|'not_scheduled'|'idle'|'unknown';status_label:string;tone:string;status_recorded_at:string|null;last_production_at:string|null;job:LiveJob|null;changeover:LiveChangeover|null;last_hour:HourSlot|null;trend:HourSlot[]}
export interface LiveSnapshot {
 generated_at:string;timezone:string;shift:LiveWindow;recording_note:string;latest_submission_at:string|null;period:LiveWindow;
 weekly:{week_start:string;window:LiveWindow;site:string;target_tonnes:number|null;actual_tonnes:number|null;progress_percent:number|null;confirmed_readings:number;excluded_readings:number;boundary_readings:number;notes:string;set_by:string|null;method:string};
 lines:LiveLine[];
 summary:{status_counts:Record<string,number>;ongoing_faults:number;planned_minutes:number;unplanned_minutes:number;planned_events:number;unplanned_events:number;changeover_minutes:number;average_percent:number|null;eligible_lines:number;previous_percent:number|null;average_method:string;today_start:string};
 issues:{id:number;line:string;machine:string;reason:string;opened_at:string;open_minutes:number;engineering_status:string;engineer:string|null;production_stopped:boolean}[];
 breakdowns:{line:string;unplanned_minutes:number;breakdowns:{category:string;minutes:number;events:number;records:{id:number;source:string;machine:string;reason:string;minutes:number}[]}[]}[];
 thresholds:{amber:number;green:number};breakdown_method:string;
}
