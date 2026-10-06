"""Agreed business examples. Pure synthetic inputs; no database connection."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from src import pulse_calculations as c

START = datetime(2026, 1, 12, 6, tzinfo=timezone.utc)
def t(minutes): return START + timedelta(minutes=minutes)
def review(actual=3000, planned=(), unplanned=(), operating=(), **kw):
    return c.reconcile_production(100, t(0), t(60), actual, planned, unplanned, operating, **kw)
def setting(id, minute, speed, supersedes=None):
    return dict(id=id, effective_at=t(minute), new_speed_ppm=D(speed), supersedes_id=supersedes)

def test_fixed_standard_and_gap_ignore_reported_setting():
    r = review(5700, operating=c.operating_timeline([setting(1,0,100),setting(2,30,90)]))
    assert r['target_packs'] == 6000
    assert 'raw_speed_deficit_packs' not in r
    assert r['remaining_gap_packs'] == 300

def test_retrospective_correction_does_not_change_gap_or_standard():
    original = [setting(1,0,100),setting(2,30,90)]
    corrected = original + [setting(3,20,80,2)]
    assert review(operating=original)['remaining_gap_packs'] == 3000
    r = review(operating=c.operating_timeline(corrected))
    assert r['remaining_gap_packs'] == 3000 and r['target_packs'] == 6000

def test_planned_precedence_and_stop_union_ignore_settings():
    r = review(planned=[(t(0),t(10))],unplanned=[(t(5),t(15))],
               operating=c.operating_timeline([setting(1,0,90)]))
    assert (r['planned_minutes'],r['unplanned_minutes']) == (10,5)
    assert (r['raw_planned_packs'],r['raw_unplanned_packs']) == (1000,500)
    assert r['target_packs'] == 6000

def test_two_minute_stop_and_notes_do_not_hide_28_minute_residual():
    for note in (None,'unknown','slow running'):
        r=review(planned=[(t(10),t(12))],note=note)
        assert (r['remaining_gap_packs'],r['equivalent_minutes'],r['prompt_required']) == (2800,28,True)
        assert r['reported_explanation'] == note

def test_raw_excess_capped_allocations_and_no_negative_residual():
    r=review(5900,planned=[(t(0),t(10))],unplanned=[(t(20),t(30))])
    assert r['raw_planned_packs'] == r['raw_unplanned_packs'] == 1000
    assert (r['allocated_planned_packs'],r['allocated_unplanned_packs']) == (100,0)
    assert r['excess_modelled_packs'] == 1900 and r['remaining_gap_packs'] == 0

def test_later_overproduction_does_not_erase_earlier_shortfall():
    total=c.summarise_reconciliations([review(5500),review(6500)])
    assert total['signed_variance_packs'] == 0
    assert total['shortfall_packs'] == total['overproduction_packs'] == 500
    assert total['remaining_gap_packs'] == 500

def test_above_standard_setting_has_no_quantified_deficit():
    r=review(operating=c.operating_timeline([setting(1,0,90),setting(2,30,110)]))
    assert 'raw_speed_deficit_packs' not in r

def test_partial_hour_threshold_before_rounding_and_decimal_pallets():
    cfg=c.PackConfig(D(100),D(10),D(10),D('0.5'))
    actual=cfg.pallets_to_packs(D('5.0001'))
    r=c.reconcile_production(100,t(0),t(15),actual)
    assert not r['prompt_required'] and c.reconciliation_api(r)['equivalent_minutes']==10
    assert c.reconcile_production(100,t(0),t(15),500)['prompt_required']
    assert cfg.packs_to_tonnes(actual)==D('0.250005')

def test_missing_is_not_zero_and_legacy_standard_is_unknown():
    assert review(None)['shortfall_packs'] is None
    r=c.reconcile_production(None,t(0),t(60),3000)
    assert r['target_packs'] is None and r['actual_packs']==3000 and not r['comparable']
    assert not c.summarise_reconciliations([r,review(None)])['coverage_complete']

def test_not_scheduled_and_crossing_carried_fault_clipped_once():
    r=review(1000,unplanned=[(t(-20),t(40)),(t(10),t(20))],not_scheduled=[(t(30),t(60))])
    assert r['target_packs']==3000 and r['unplanned_minutes']==30
    assert r['raw_unplanned_packs']==3000 and r['excess_modelled_packs']==1000


def test_cross_surface_carried_fault_and_unknown_note():
    from src import dashboard_reports, hourly_reports
    from src.factory_time import current_shift_window
    now=t(65)
    run=dict(id=2,production_line='Rovema',line_technician='Liam',shift='Day',
             customer='Synthetic',product='Rice',format='Pillow',pack_weight_kg=D(1),
             packs_per_case=10,cases_per_pallet=100,target_speed_ppm=D(100),standard_speed_ppm=D(100),
             status='Completed',started_at=t(0),finished_at=t(60),pallets_remaining=D(0),total_pallets_completed=D(3))
    fault=dict(id=1,production_run_id=1,production_line='Rovema',machine='Casepacker',reason='Jam',
               opened_at=t(0),resolved_at=t(2),production_status='Resolved')
    reading=dict(production_run_id=2,hour_start=t(0),pallets_completed=D(3),other_loss_reason='unknown')
    window=current_shift_window(now)
    hourly=hourly_reports.build_hourly_report(dict(lines=['Rovema'],runs=[run],readings=[reading],
        speed_changes=[],planned=[],faults=[fault],stoppages=[]),window,now)
    tablet=review(unplanned=[(t(0),t(2))],note='unknown')
    dashboard=dashboard_reports.build_gap_attribution(dict(lines=['Rovema'],runs=[run],
        hourly=[dict(production_run_id=2,period_started_at=t(0),period_ended_at=t(60),expected_packs=D(123),actual_pallets=D(3),other_loss_reason='unknown')],
        planned=[],faults=[fault],xray=[],legacy_hourly_without_timestamp=0),window,now)
    hr=hourly['lines'][0]['hours'][0]['runs'][0]['reconciliation']
    dr=dashboard['site']['reconciliation']
    assert hr['target_packs']==dr['target_packs']==tablet['target_packs']==6000
    assert hr['remaining_gap_packs']==dr['remaining_gap_packs']==tablet['remaining_gap_packs']==2800
    assert dr['reported_explanations']==['unknown']
    # Neither stale stored expected packs nor the originating run ID changes the result.


def test_zero_length_end_boundary_is_not_an_hour_of_loss():
    r=c.reconcile_production(100,t(60),t(60),0)
    assert r['target_packs']==0 and not r['prompt_required']


def test_management_130_reported_110_does_not_allocate_gap():
    reports = [dict(setting(1, 0, 110), changed_by="Liam", reason="Reported reduction", submitted_at=t(30))]
    baseline = c.reconcile_production(130, t(0), t(60), 6600, unplanned=[(t(0),t(2))])
    result = c.reconcile_production(130, t(0), t(60), 6600, unplanned=[(t(0),t(2))], operating=reports)
    assert (result['target_packs'], result['raw_unplanned_packs'], result['remaining_gap_packs']) == (7800, 260, 940)
    assert result['equivalent_minutes'] == D(940)/D(130)
    assert {k:v for k,v in result.items() if k != 'operating_context'} == {k:v for k,v in baseline.items() if k != 'operating_context'}
    context = result['operating_context'][0]
    assert context['speed_ppm'] == 110 and context['changed_by'] == 'Liam'
    assert context['reason'] == 'Reported reduction' and context['effective_at'] == t(0).isoformat()


def test_corrections_and_settings_never_change_arithmetic():
    reports = [setting(1,0,100),setting(2,10,0),setting(3,20,200,2)]
    with_reports = review(operating=reports)
    without = review()
    assert {k:v for k,v in with_reports.items() if k != 'operating_context'} == {k:v for k,v in without.items() if k != 'operating_context'}
    assert with_reports['operating_context'][1]['superseded']
    assert with_reports['operating_context'][2]['supersedes_id'] == 2
