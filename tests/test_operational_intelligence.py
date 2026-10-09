"""Operational evidence and financial entitlement boundaries; no live database."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from scripts.manual_integration.live_dashboard_fixtures import source, NOW
from src import operational_intelligence as oi, intelligence_api, management_auth
from src.live_dashboard import reporting_week
from src.api import app

WEEK = reporting_week(date(2026, 10, 5))

def build(data=None, **kwargs):
    return oi.build_intelligence(source() if data is None else data, WEEK, NOW, **kwargs)


def test_real_weights_targets_and_statuses():
    result = build()
    assert result['weekly']['actual_tonnes'] == pytest.approx(97.212)
    assert result['weekly']['progress_percent'] == pytest.approx(81.01)
    assert [r['status'] for r in result['lines']] == ['running', 'changeover', 'stopped']
    assert result['lines'][0]['last_hour']['line']['output_vs_target_percent'] == 90
    assert result['lines'][0]['job']['remaining_pallets'] == pytest.approx(11.368)
    assert result['output_gap']['unclassified_tonnes'] == result['output_gap']['total_tonnes']
    assert all(result['output_gap'][k] is None for k in ['recoverable_tonnes','delayed_tonnes','confirmed_unrecovered_tonnes'])
    assert [r['tonnes'] for r in result['material_flow']] == [None,None,97.212,None,None]


def test_downtime_fault_overlap_is_counted_once_and_causes_are_recorded():
    result = build()
    assert result['downtime']['planned_minutes'] == 35
    # Guill's 25-minute second fault overlaps its 48-minute first fault completely.
    assert result['downtime']['unplanned_minutes'] == 48 + 25
    assert result['loss_drivers'][0]['cause'] == 'Film tracking fault'
    assert result['loss_drivers'][0]['minutes'] == 48
    assert result['loss_drivers'][0]['fault_ids'] == [1]
    assert all(r['estimated_tonnes'] is None for r in result['loss_drivers'])


def test_planned_overlap_and_not_scheduled_excluded():
    data = source()
    data['planned'].append(dict(id=9, production_run_id=3, reason='Break', started_at=NOW-timedelta(minutes=40), ended_at=NOW-timedelta(minutes=20)))
    data['stoppages'].append(dict(id=10, production_line='Guill', kind='not_scheduled', started_at=NOW-timedelta(minutes=10), ended_at=None))
    result = build(data)
    assert result['downtime']['planned_minutes'] == 55
    assert result['downtime']['unplanned_minutes'] == 43
    assert result['downtime']['not_scheduled_minutes'] == 10
    assert result['downtime']['unplanned_percent'] == pytest.approx(43/98*100)


def test_empty_records_are_not_zero_production_or_zero_recoverable_loss():
    data=source()
    for key in ['runs','readings','planned','faults','stoppages','targets']: data[key]=[]
    result=build(data)
    assert result['weekly']['actual_tonnes'] is None
    assert result['weekly']['target_tonnes'] is None
    assert result['output_gap']['total_tonnes'] is None
    assert result['loss_drivers'] == []
    assert result['downtime']['unplanned_percent'] is None


def test_duplicate_partial_reading_uses_historical_conversion_once():
    data=source()
    data['runs']=data['runs'][:1]
    data['runs'][0].update(pack_weight_kg=Decimal('.5'),packs_per_case=8,cases_per_pallet=50)
    row=deepcopy(data['readings'][0]); row.update(pallets_completed=Decimal('3'),period_ended_at=row['period_started_at']+timedelta(minutes=27))
    data['readings']=[row,{**row,'id':999,'pallets_completed':Decimal('4')}]
    result=oi.weekly_values(data,WEEK,NOW,None)
    assert result['actual_tonnes'] == pytest.approx(.8)
    assert result['confirmed_readings'] == 1


def test_line_target_is_not_invented_from_site_target():
    data=source()
    assert build(data,line='Rovema')['weekly']['target_tonnes'] is None
    data['line_targets']=[dict(week_start=date(2026,10,5),scope='line',production_line='Rovema',target_tonnes=60)]
    result=build(data,line='Rovema')
    assert result['weekly']['target_tonnes'] == 60
    assert result['weekly']['actual_tonnes'] == pytest.approx(52.632)
    assert [r['name'] for r in result['lines']] == ['Rovema']


def test_comparison_requires_matching_reported_coverage():
    data=source()
    previous=[]
    for row in data['readings']:
        older={**row,'id':row['id']+1000,'pallets_completed':row['pallets_completed']/2}
        for key in ['hour_start','period_started_at','period_ended_at','shift_window_start','created_at']: older[key]-=timedelta(days=7)
        previous.append(older)
    data['readings']+=previous
    assert oi.weekly_values(data,WEEK,NOW,None)['comparison_percent'] == pytest.approx(100)
    data['readings'].pop()
    assert oi.weekly_values(data,WEEK,NOW,None)['comparison_percent'] is None


def test_adjacent_windows_do_not_duplicate_readings():
    data=source()
    previous=reporting_week(date(2026,9,28))
    old=deepcopy(data['readings'][0]);old['id']=999
    old['shift_window_start']=WEEK.start-timedelta(hours=8)
    old['period_started_at']=WEEK.start-timedelta(minutes=30)
    old['period_ended_at']=WEEK.start+timedelta(minutes=30)
    data['readings']=[old]
    assert not oi.selected_readings(data,WEEK,NOW)
    assert oi.selected_readings(data,previous,NOW)==[old]


def test_elapsed_week_uses_timezone_and_dst_boundaries():
    week=reporting_week(date(2026,10,24))
    assert (week.end-week.start).total_seconds()/3600 == 169
    now=week.start+timedelta(hours=84.5)
    result=oi.weekly_values(source(),week,now,None)
    assert result['elapsed_percent']==50


def test_zero_output_is_known_not_missing_and_above_target_not_capped():
    data=source()
    for row in data['readings']:row['pallets_completed']=Decimal(0)
    assert build(data)['weekly']['actual_tonnes']==0
    for row in data['readings']:row['pallets_completed']=Decimal(100)
    assert build(data)['weekly']['progress_percent']>100


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(management_auth,'MANAGEMENT_PIN','1234')
    management_auth._sessions.clear()
    token=management_auth.create_session('Preview')['token']
    monkeypatch.setattr(oi,'load_data',lambda now:(source(),WEEK))
    yield TestClient(app,headers={'Authorization':f'Bearer {token}'})
    management_auth._sessions.clear()


def test_server_rejects_financial_flags_and_has_no_financial_results(client):
    for suffix in ['', '?financial_intelligence=true', '?phase=2&scope=admin']:
        assert client.get('/api/v1/dashboard/financial-intelligence'+suffix).status_code==403
    assert intelligence_api.deployment_capabilities()['financial_intelligence'] is False
    result=client.get('/api/v1/dashboard/operational-intelligence')
    assert result.status_code==200,result.text
    assert result.json()['capabilities']['financial_intelligence'] is False
    assert 'cost_per_tonne' not in result.text


def test_api_validates_scope_and_reports_safe_errors(client,monkeypatch):
    assert client.get('/api/v1/dashboard/operational-intelligence?production_line=UNKNOWN').status_code==422
    assert client.get('/api/v1/dashboard/operational-intelligence?window=all_history').status_code==422
    def fail(now):raise RuntimeError('database secret should not appear')
    monkeypatch.setattr(oi,'load_data',fail)
    response=client.get('/api/v1/dashboard/operational-intelligence')
    assert response.status_code==503
    assert 'secret' not in response.text
