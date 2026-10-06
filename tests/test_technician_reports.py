from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from src.technician_reports import build_technician_performance

START=datetime(2026,1,12,6,tzinfo=timezone.utc)
def t(m): return START+timedelta(minutes=m)
def run(**extra):
 return dict(id=1,line_technician='Liam',production_line='Rovema',shift='Days',product='Rice',customer='Customer',
  started_at=t(0),finished_at=t(60),standard_speed_ppm=D(130),target_speed_ppm=D(5),
  packs_per_case=10,cases_per_pallet=100,pack_weight_kg=D(1),**extra)
def reading(start=0,end=60,pallets='6.6',rid=1):
 return dict(production_run_id=rid,period_started_at=t(start) if start is not None else None,
  period_ended_at=t(end) if end is not None else None,pallets_completed=D(pallets))
def report(runs=None,readings=None,planned=(),faults=()):
 return build_technician_performance(runs or [run()],readings if readings is not None else [reading()],planned,faults)[0]

def test_preserved_standard_not_legacy_target_or_stored_expectations():
 r=report()
 assert r['expected_tonnes']==7.8 and r['actual_tonnes']==6.6
 assert r['target_achievement_percent']==84.6 and r['coverage_complete']

def test_missing_hour_or_unknown_standard_is_not_rankable():
 r=report(readings=[reading(0,30,'3')])
 assert r['data_completion_rate_percent']==50 and r['target_achievement_percent'] is None
 old=run();old['standard_speed_ppm']=None
 r=report(runs=[old]);assert r['reported_tonnes']==6.6 and r['target_achievement_percent'] is None

def test_overlapping_carried_faults_stop_at_production_restart():
 faults=[dict(production_run_id=99,production_line='Rovema',opened_at=t(-10),resolved_at=t(10),engineering_status='Ongoing'),
         dict(production_run_id=1,production_line='Rovema',opened_at=t(5),resolved_at=t(15),engineering_status='Resolved')]
 planned=[dict(production_run_id=1,started_at=t(0),ended_at=t(5))]
 r=report(planned=planned,faults=faults)
 assert r['planned_downtime_minutes']==5 and r['unplanned_downtime_minutes']==10

def test_later_overproduction_does_not_erase_shortfall():
 r=report(readings=[reading(0,30,'3.4'),reading(30,60,'4.4')])
 assert r['target_achievement_percent']==100 and r['output_gap_tonnes']==0.5

def test_legacy_untimed_actual_retained_but_not_compared():
 r=report(readings=[reading(None,None)])
 assert r['reported_tonnes']==6.6 and not r['coverage_complete']

def test_overlapping_readings_cannot_create_a_false_ranking():
 r=report(readings=[reading(),reading()])
 assert not r['coverage_complete'] and r['target_achievement_percent'] is None
