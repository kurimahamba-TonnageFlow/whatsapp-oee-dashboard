import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.api import app
from src import hmi_auth
from src.catalogue import aliases, canonical
from src.task_capture_api import Observation

@pytest.fixture
def secured(monkeypatch):
    app.dependency_overrides.pop(hmi_auth.require_hmi_access, None)
    monkeypatch.setenv("HMI_DEVICE_PIN", "synthetic-tablet-secret")
    hmi_auth._sessions.clear(); hmi_auth._attempts.clear()
    return TestClient(app)

@pytest.mark.parametrize("path", ["/api/v1/runs", "/api/v1/runs/1/hourly-updates", "/api/v1/faults/1/production-restored", "/api/v1/lines/Rovema/stoppages", "/api/v1/task-observations"])
def test_unauthenticated_tablet_cannot_mutate(secured,path):
    assert secured.post(path,json={}).status_code == 401

def test_tablet_expiry_logout_and_wrong_role(secured):
    result=secured.post("/api/v1/hmi-access/login",json={"pin":"synthetic-tablet-secret","device_name":"Rovema tablet"})
    assert result.status_code==200
    token=result.json()["token"]
    headers={"X-HMI-Session":token}
    assert secured.get("/api/v1/hmi-access/session",headers=headers).status_code==200
    assert secured.get("/api/v1/management/production-standards",headers=headers).status_code==401
    hmi_auth._sessions[token]["expires_at"]=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert secured.get("/api/v1/hmi-access/session",headers=headers).status_code==401
    token=secured.post("/api/v1/hmi-access/login",json={"pin":"synthetic-tablet-secret","device_name":"Rovema"}).json()["token"]
    secured.post("/api/v1/hmi-access/logout",headers={"X-HMI-Session":token})
    assert token not in hmi_auth._sessions

def test_tablet_login_limits_attempts(secured):
    for _ in range(5):
        assert secured.post("/api/v1/hmi-access/login",json={"pin":"wrong","device_name":"Rovema"}).status_code==401
    assert secured.post("/api/v1/hmi-access/login",json={"pin":"synthetic-tablet-secret","device_name":"Rovema"}).status_code==429

def test_catalogue_matches_legacy_without_rewriting():
    assert canonical("product","White Bas")=="White Basmati"
    assert canonical("customer","Morissons")=="Morrisons"
    assert set(aliases("shift","Nights"))=={"night","nights"}
    assert set(aliases("product","White Long Grain Easy Cook"))=={"white lg easy cook","white long grain easy cook"}

def test_task_rejects_zero_future_missing_context_and_excess_waiting():
    now=datetime.now(timezone.utc)
    values=dict(task="Film change",technician="Liam",started_at=now-timedelta(minutes=10),ended_at=now,
                product="Rice",from_configuration="1kg x10",to_configuration="1kg x10",waiting_minutes=0,
                shared_work=False,completed_successfully=True,notes="")
    assert Observation(**values).production_line=="Rovema"
    for patch in ({"started_at":now},{"ended_at":now+timedelta(days=1)},
                  {"from_configuration":" "},{"waiting_minutes":20},{"shared_work":True}):
        with pytest.raises(ValueError): Observation(**{**values,**patch})


def test_production_launcher_refuses_placeholders_shared_secrets_and_multiple_workers():
    from src.serve import validate_environment
    valid=dict(MANAGEMENT_PIN='management-secret',ENGINEERING_PIN='engineering-secret',HMI_DEVICE_PIN='tablet-secret',DATABASE_URL='postgresql://configured')
    validate_environment(valid)
    for overrides in ({'WEB_CONCURRENCY':'2'},{'MANAGEMENT_PIN':'2468'},{'HMI_DEVICE_PIN':'management-secret'},{'DATABASE_URL':''}):
        with pytest.raises(ValueError):
            validate_environment({**valid,**overrides})
