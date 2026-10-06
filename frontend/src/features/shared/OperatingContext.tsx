export interface OperatingReport {
  period_start: string
  period_end: string
  run_id?: number
  report_id?: number
  speed_ppm: number
  effective_at: string
  submitted_at?: string | null
  reason?: string
  changed_by?: string
  supersedes_id?: number | null
  superseded?: boolean
}

export function OperatingContext({ reports }: { reports?: OperatingReport[] }) {
  if (!reports?.length) return null
  return <div>
    <p>Reported machine settings are context only. They do not allocate the production gap.</p>
    {reports.map((r, i) => <p key={`${r.run_id}-${r.report_id}-${r.period_start}-${i}`}>
      Period {r.period_start} to {r.period_end}: {r.speed_ppm} packs/minute reported by {r.changed_by}.
      Effective {r.effective_at}. Submitted {r.submitted_at ?? 'Not recorded'}. Reason: {r.reason}.
      {r.superseded && ' Superseded report retained for audit.'}
      {r.supersedes_id != null && ` Corrects report ${r.supersedes_id}.`}
    </p>)}
  </div>
}
