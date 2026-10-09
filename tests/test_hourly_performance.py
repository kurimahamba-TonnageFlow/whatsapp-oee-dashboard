from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import pytest
from src import hourly_performance as h
from src import pulse_calculations as c

START = datetime(2026,10,9,tzinfo=timezone.utc)
def stop(a,b,reason="Film Change"):
    return {"started_at":START+timedelta(minutes=a),"ended_at":START+timedelta(minutes=b),"reason":reason}
def fault(a,b):
    return {"opened_at":START+timedelta(minutes=a),"resolved_at":START+timedelta(minutes=b),"reason":"Infeed"}
def report(actual=6000,duration=60,planned=None,faults=None,**kw):
    return h.period_report(100,START,START+timedelta(minutes=duration),actual,
                           [] if planned is None else planned,[] if faults is None else faults,**kw)

@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('PULSE_TRIAL_QUALITY_PERCENT','98')
    monkeypatch.setenv('PULSE_OEE_EXCLUDED_PLANNED_REASONS','')

def test_full_hour_at_standard():
    r=report();o=h.aggregate_oee([r])
    assert r['target_packs']==6000 and r['pack_variance']==0
    assert [o[k] for k in ('availability_percent','performance_percent','estimated_quality_percent','estimated_oee_percent')]==[100,100,98,98]
    assert o['quality_basis']=='provisional'

def test_unplanned_downtime():
    r=report(actual=5000,faults=[fault(0,10)])
    o=h.aggregate_oee([r])
    assert r['shortfall_packs']==1000 and r['unexplained_shortfall']==0
    assert o['availability_percent']==83.3 and o['performance_percent']==100 and o['estimated_oee_percent']==81.7

def test_partial_hour_and_zero_output():
    r=report(actual=2700,duration=27)
    assert r['target_packs']==2700 and h.aggregate_oee([r])['estimated_oee_percent']==98
    z=report(actual=0)
    assert z['shortfall_packs']==6000 and h.aggregate_oee([z])['estimated_oee_percent']==0

def test_missing_downtime_and_zero_operating_time():
    r=h.period_report(100,START,START+timedelta(hours=1),1000,None,None)
    assert h.aggregate_oee([r])['unavailable_reason']=='Awaiting downtime data'
    r=report(actual=0,faults=[fault(0,60)])
    assert h.aggregate_oee([r])['estimated_oee_percent'] is None

def test_only_configured_exclusions_and_overlap(monkeypatch):
    planned=[stop(0,10)]
    r=report(actual=4000,planned=planned,faults=[fault(5,20)])
    assert r['planned_minutes']==10 and r['unplanned_minutes']==10 and r['excluded_minutes']==0
    assert h.aggregate_oee([r])['availability_percent']==83.3
    monkeypatch.setenv('PULSE_OEE_EXCLUDED_PLANNED_REASONS','Film Change')
    r=report(actual=4000,planned=planned,faults=[fault(5,20)])
    assert r['target_packs']==6000 and r['excluded_minutes']==10
    assert h.aggregate_oee([r])['availability_percent']==80

def test_above_target_is_not_capped():
    o=h.aggregate_oee([report(actual=12000)])
    assert o['performance_percent']==200 and o['estimated_oee_percent']==196
    assert o['warnings']

def test_measured_rejects_use_gross_for_performance():
    o=h.aggregate_oee([report(actual=5700,gross_packs=6000,rejected_packs=300)])
    assert o['performance_percent']==100 and o['estimated_quality_percent']==95 and o['estimated_oee_percent']==95
    assert o['quality_basis']=='measured'

def test_invalid_quality_config(monkeypatch):
    monkeypatch.setenv('PULSE_TRIAL_QUALITY_PERCENT','oops')
    assert h.aggregate_oee([report()])['estimated_oee_percent'] is None

def test_original_338_example_and_pallet_conversion():
    start=datetime.fromisoformat('2026-10-09T00:32:56.741521+00:00')
    end=datetime.fromisoformat('2026-10-09T01:00:00+00:00')
    packs=c.PackConfig(D(120),D(10),D(220),D(1)).pallets_to_packs(D(5))
    r=h.period_report(120,start,end,packs,[],[])
    assert packs==11000
    assert abs(r['target_packs']-D('3246.516958'))<D('.00001')
    assert c.as_number(r['attainment_percent'],D('.1'))==338.8
    assert r['shortfall_packs']==0 and r['unexplained_shortfall'] is None

def test_card_dashboard_aggregation_uses_same_weighted_formula():
    a,b=report(actual=5000,faults=[fault(0,10)]),report(actual=6000)
    assert h.aggregate_oee([a,b])['estimated_oee_percent']==89.8
