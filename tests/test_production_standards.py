"""Offline API checks; database history/selection additionally rehearsed on synthetic PostgreSQL."""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from src.api import app
from src import database, management_auth, standards_api

client = TestClient(app)
BODY = dict(production_line="Rovema",product="Rice",pack_type="Pillow",pack_weight_kg="1",
            packs_per_case=10,cases_per_pallet=100,standard_speed_ppm="130",
            effective_at="2026-01-01T00:00:00Z",reason="Approved baseline")

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refused():
        raise AssertionError("No real database allowed")
    monkeypatch.setattr(database,"get_database_connection",refused)

@pytest.fixture
def headers():
    session = management_auth.create_session("Kuri")
    return {"Authorization":"Bearer " + session["token"], "Idempotency-Key":"test-standard-version"}


def test_standard_write_and_audit_history_require_management():
    assert client.post('/api/v1/management/production-standards',json=BODY,headers={"Idempotency-Key":"test"}).status_code == 401
    assert client.get('/api/v1/management/production-standards').status_code == 401


def test_manager_identity_is_not_taken_from_payload(monkeypatch,headers):
    seen=[]
    def record(values,manager_name,idempotency=None):
        seen.append((values,manager_name,idempotency))
        return {**values,"id":7,"manager_name":manager_name,"recorded_at":datetime.now(timezone.utc)}
    monkeypatch.setattr(standards_api,"record_standard",record)
    response=client.post('/api/v1/management/production-standards',json={**BODY,"manager_name":"Technician"},headers=headers)
    assert response.status_code==201
    assert response.json()['manager_name']=='Kuri'
    assert seen[0][0]['standard_speed_ppm']==Decimal(130)
    assert seen[0][2].key=='test-standard-version'


@pytest.mark.parametrize('change',[
 {'reason':' '}, {'effective_at':'2026-01-01T00:00:00'}, {'standard_speed_ppm':'0'},
 {'standard_speed_ppm':'NaN'}, {'packs_per_case':0}, {'production_line':'Unknown'}, {'product':' '}])
def test_invalid_standard_rejected(headers,change):
    assert client.post('/api/v1/management/production-standards',json={**BODY,**change},headers=headers).status_code==422


def test_start_request_does_not_require_technician_standard():
    from src.runs_api import StartRunRequest
    payload=dict(production_line="Rovema",line_technician="Liam",shift="Days",customer="Synthetic",
                 product="Rice",pack_weight="1kg",pack_weight_kg=1,packs_per_case=10,
                 pack_type="Pillow",cases_per_pallet=100,pallets_remaining=10,previous_run_completed=0)
    assert StartRunRequest(**payload).target_speed_ppm is None
