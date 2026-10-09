from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from src.api import app
from src import linetech_api as api, management_auth, pulse_capture_api as capture
from src.linetech import LineTechConfig, prepare_changeover, validate_config_references


def config():
    return LineTechConfig(enabled=True, groups=[{"key": key, "label": key, "equipment": []}
        for key in ["sbs", "xray", "casepacker", "robot"]], products=["White Basmati", "Brown Basmati"],
        formats=["1 kg x 10", "1 kg x 8"], sizes=["0.5", "1", "2"]).model_dump()


@pytest.mark.parametrize("kind,value,engineering", [("product", "Brown Basmati", False), ("format", "1 kg x 8", True), ("size", "0.5", True)])
def test_changeover_intent_uses_current_run_and_configuration(kind, value, engineering):
    result = prepare_changeover(config(), {"kind": kind, "next_value": value},
        {"product": "White Basmati", "format": "1 kg x 10", "pack_weight_kg": Decimal("1")})
    assert result["engineering_required"] is engineering
    assert result["qa_status"] == "awaiting_verification"
    assert result["verification"] is None


@pytest.mark.parametrize("selection", [{"kind": "size", "next_value": "1"}, {"kind": "format", "next_value": "unconfigured"}])
def test_invalid_or_unchanged_configuration_rejected(selection):
    with pytest.raises(ValueError):
        prepare_changeover(config(), selection, {"product": "White Basmati", "format": "1 kg x 10", "pack_weight_kg": 1})


def test_product_engineering_is_explicitly_configurable():
    settings = {**config(), "product_engineering_required": True}
    assert prepare_changeover(settings, {"kind": "product", "next_value": "Brown Basmati"}, {"product": "White Basmati"})["engineering_required"]


def test_configuration_cannot_assign_foreign_fault_button():
    settings = config()
    settings["groups"][0]["equipment"] = [{"machine_id": 1, "label": "BV1", "categories": [{"name": "Film", "button_ids": [999]}]}]
    with pytest.raises(ValueError, match="another machine"):
        validate_config_references(LineTechConfig.model_validate(settings), [{"id": 1, "buttons": [{"id": 2, "event_type": "unplanned_fault"}]}])


def test_config_requires_management_authentication():
    assert TestClient(app).get('/api/v1/management/lines/Rovema/linetech').status_code == 401


def test_new_changeover_selection_reaches_existing_transaction(monkeypatch):
    calls = []
    def write(*args, **kwargs):
        calls.append(kwargs)
        raise capture.PulseCaptureError(409, "End run first")
    monkeypatch.setattr(capture, 'start_line_stoppage', write)
    response = TestClient(app).post('/api/v1/lines/Rovema/stoppages', headers={'Idempotency-Key': 'linetech-changeover-key'},
        json={'kind': 'changeover', 'started_by': 'Liam', 'changeover_selection': {'kind': 'format', 'next_value': '1 kg x 8'}})
    assert response.status_code == 409
    assert calls[0]['changeover_selection']['kind'] == 'format'


def test_resolved_preset_needs_actual_restart_but_comment_is_optional():
    value = capture.FaultReportRequest(reported_by='Liam', machine='SBS Bagger BV1', reason='Film torn', machine_id=1, button_id=2,
        outcome='resolved', started_at='2026-10-09T08:00:00Z', restored_at='2026-10-09T08:02:00Z')
    assert value.note is None
    with pytest.raises(ValueError):
        capture.FaultReportRequest(reported_by='Liam', machine='SBS Bagger BV1', reason='Film torn', machine_id=1, button_id=2, outcome='resolved')


def test_other_fault_requires_description():
    with pytest.raises(ValueError):
        capture.FaultReportRequest(reported_by='Liam', machine='SBS Bagger BV1', reason='Other Fault', machine_id=1)


def test_repair_can_be_recorded_without_claiming_production_restarted():
    value = capture.FaultReportRequest(reported_by='Liam',machine='SBS Bagger BV1',reason='Film Torn',machine_id=1,button_id=2,
        outcome='resolved_waiting_restart',started_at='2026-10-09T08:00:00Z')
    assert value.restored_at is None and value.note is None


def test_additive_fields_preserve_pre_upgrade_retry_fingerprint():
    from src.api_idempotency import build_idempotency
    from pydantic import BaseModel
    class LegacyPlanned(BaseModel):
        reason: str
        started_by: str
    old = LegacyPlanned(reason='Film Change',started_by='Liam')
    new = capture.PlannedDowntimeStartRequest(**old.model_dump())
    assert build_idempotency('same-key','planned',old,201,lambda x:x).fingerprint == build_idempotency('same-key','planned',new,201,lambda x:x).fingerprint


def test_draft_catalogue_uses_existing_fault_ids_without_inventing_presets():
    draft=api.initial_config([{'id':4,'name':'X-ray / Checkweigher','active':True,'buttons':[{'id':7,'name':'Machine jam','event_type':'unplanned_fault'}]}])
    assert draft['enabled'] is False
    assert draft['groups'][1]['equipment'][0]['categories'][0]['button_ids'] == [7]
    assert len(draft['groups']) == 4


def test_sheet_install_requires_management_authentication():
    assert TestClient(app).post('/api/v1/management/lines/Rovema/linetech/sheet-presets', headers={'Idempotency-Key':'sheet-test'}).status_code == 401


def test_sheet_preset_is_scoped_to_rovema():
    from src.linetech_presets import rovema_preset
    preset=rovema_preset()
    assert preset['line']=='Rovema'
    assert len(preset['machines'])==6
    assert all(p['active'] for p in preset['planned'])
    assert not any(p['reason']=='Changeover' for p in preset['planned'])


def test_sheet_endpoint_rejects_other_lines():
    app.dependency_overrides[management_auth.require_management_session]=lambda:'Test manager'
    try:
        response=TestClient(app).post('/api/v1/management/lines/GIC/linetech/sheet-presets',headers={'Idempotency-Key':'sheet-test'})
        assert response.status_code==422
    finally:
        app.dependency_overrides.pop(management_auth.require_management_session,None)
