export interface FaultCategory { name: string; button_ids: number[]; active: boolean }
export interface Equipment { machine_id: number; label: string; categories: FaultCategory[]; active: boolean }
export interface MachineGroup { key: 'sbs'|'xray'|'casepacker'|'robot'; label: string; equipment: Equipment[] }
export interface PlannedReason { reason: string; components: string[]; active: boolean }
export interface LineTechConfig {
 enabled: boolean; groups: MachineGroup[]; planned: PlannedReason[];
 products: string[]; formats: string[]; sizes: string[]; product_engineering_required: boolean;
}
export interface ChangeoverSelection { kind: 'product'|'format'|'size'; next_value: string }
export interface ChangeoverWorkflow extends ChangeoverSelection {
 previous_value: string | null; engineering_required: boolean; qa_status: string;
 cancelled_at: string | null; cancelled_by?: string; cancellation_reason?: string;
 verification: { technician: string; reference: string; recorded_at: string } | null;
}
