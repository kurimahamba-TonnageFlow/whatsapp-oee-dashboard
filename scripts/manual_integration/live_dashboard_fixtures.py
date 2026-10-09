"""Deterministic, synthetic preview data through the production calculation layer."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone,date
from decimal import Decimal
from pathlib import Path
import json
from fastapi.encoders import jsonable_encoder
from src.live_dashboard import build_snapshot,reporting_week

NOW=datetime(2026,10,9,10,20,tzinfo=timezone.utc)
END=NOW.replace(minute=0)

def source():
    data=dict(lines=['Rovema','GIC','Guill'],runs=[],readings=[],planned=[],faults=[],stoppages=[],operating_changes=[],speed_changes=[],targets=[dict(week_start=date(2026,10,5),scope='site',production_line=None,target_tonnes=Decimal('120'),notes='Synthetic weekly plan',set_by='Preview manager')])
    for i,(line,speed,customer,product,ratio) in enumerate([('Rovema',120,'Aldi','White Basmati',90),('GIC',100,'Waitrose','Basmati',60),('Guill',80,'Tesco','Brown Basmati',38)],1):
        quantities=[]
        for h in range(8):
            start=END-timedelta(hours=8-h)
            percent=ratio+[0,3,-4,6,2,-1,5,0][h]
            pallets=Decimal(speed*60*percent)/100/1000
            quantities.append(pallets)
            data['readings'].append(dict(id=i*100+h,production_run_id=i,hour_start=start,period_started_at=start,period_ended_at=start+timedelta(hours=1),shift_window_start=NOW.replace(hour=5,minute=0),pallets_completed=pallets,created_at=start+timedelta(hours=1)))
        completed=sum(quantities)
        data['runs'].append(dict(id=i,production_line=line,line_technician='Liam',shift='Days',customer=customer,product=product,format='1 kg x 10',pack_type='Bag',pack_weight_kg=Decimal('1'),packs_per_case=10,cases_per_pallet=100,target_speed_ppm=Decimal(speed),standard_speed_ppm=Decimal(speed),started_at=END-timedelta(hours=8),finished_at=NOW-timedelta(minutes=15) if line=='GIC' else None,status='Finished' if line=='GIC' else 'Active',starting_pallets_remaining=Decimal('64'),pallets_remaining=Decimal('64')-completed,total_pallets_completed=completed))
    for i,line,machine,reason,age,resolved,engineer,category in [(1,'Guill','Bagger','Film tracking fault',48,None,'Alfie','Mechanical'),(2,'Guill','X-ray','Reject sensor fault',25,None,None,'Quality / CCP'),(3,'Rovema','BV2','Vertical seal adjustment',95,70,'Ben','Machine setting')]:
        data['faults'].append(dict(id=i,production_run_id=3 if line=='Guill' else 1,production_line=line,machine=machine,reason=reason,opened_at=NOW-timedelta(minutes=age),resolved_at=NOW-timedelta(minutes=resolved) if resolved else None,production_status='Resolved' if resolved else 'Ongoing',engineering_status='In Progress' if engineer else 'Not Started',engineer_called=True,engineer=engineer,fault_category=category))
    data['planned']=[dict(id=1,production_run_id=2,reason='Film change',started_at=NOW-timedelta(hours=2),ended_at=NOW-timedelta(hours=2)+timedelta(minutes=20))]
    data['stoppages']=[dict(id=1,production_line='GIC',kind='changeover',reason=None,started_at=NOW-timedelta(minutes=15),ended_at=None,physical_ended_at=None,reference_speed_ppm=100,workflow={'kind':'format','qa_status':'awaiting_verification'},changeover_engineer='Marina',engineering_ready_at=None)]
    return data

def main():
    data=source();variants={'normal':data}
    empty=deepcopy(data)
    for key in ['runs','readings','planned','faults','stoppages','targets']:empty[key]=[]
    variants['empty']=empty
    missing=deepcopy(data);missing['readings']=[r for r in missing['readings'] if r['production_run_id']!=1 or r['hour_start']!=END-timedelta(hours=1)];variants['missing']=missing
    above=deepcopy(data);above['readings'][7]['pallets_completed']=Decimal('11');variants['above']=above
    unscheduled=deepcopy(data);unscheduled['runs']=[r for r in unscheduled['runs'] if r['id']!=2];unscheduled['readings']=[r for r in unscheduled['readings'] if r['production_run_id']!=2];unscheduled['planned']=[];unscheduled['stoppages'][0].update(kind='not_scheduled',started_at=END-timedelta(hours=8));variants['unscheduled']=unscheduled
    output={key:jsonable_encoder(build_snapshot(value,reporting_week(date(2026,10,5)),NOW)) for key,value in variants.items()}
    Path('frontend/preview/live-fixtures.json').write_text(json.dumps(output,indent=2),encoding='utf-8')

if __name__=='__main__':main()
