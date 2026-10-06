"""Casepacker HTTP validation and actor boundaries. All DB functions mocked."""
import pytest
from fastapi.testclient import TestClient
from src.api import app
from src import engineering_api as eng, engineering_auth, pulse_capture_api as capture
from src.database import PulseCaptureError

client = TestClient(app, headers={'Idempotency-Key': 'casepacker-test-key-0000001'})

@pytest.fixture
def signed_in():
    app.dependency_overrides[engineering_auth.require_engineering_session] = lambda: 'Alfie'
    yield
    app.dependency_overrides.pop(engineering_auth.require_engineering_session, None)

@pytest.mark.parametrize('payload', [
    {'kind':'changeover','casepacker_required':True},
    {'kind':'changeover','casepacker_required':True,'casepacker_details':'   '},
    {'kind':'other','reason':'Waiting','casepacker_required':True,'casepacker_details':'x8'},
    {'kind':'changeover','casepacker_required':False,'casepacker_details':'x8'},
])
def test_invalid_casepacker_request_cannot_start_timer(monkeypatch,payload):
    def forbidden(*a,**k): raise AssertionError('No write should be attempted')
    monkeypatch.setattr(capture,'start_line_stoppage',forbidden)
    response=client.post('/api/v1/lines/Rovema/stoppages',json={'started_by':'Liam',**payload})
    assert response.status_code==422


def test_engineer_actor_comes_from_session_not_body(monkeypatch,signed_in):
    calls=[]
    def save(*args,idempotency):
        calls.append((args,idempotency.action))
        return {'status':'success'}
    monkeypatch.setattr(eng,'update_casepacker_request',save)
    result=client.post('/api/v1/engineering/casepacker-requests/7/actions',json={'action':'ready','note':' Program checked ','engineer':'Aaron'})
    assert result.status_code==200
    assert calls[0][0][:4]==(7,'ready','Alfie','Program checked')
    assert calls[0][1]=='casepacker:7:Alfie'


@pytest.mark.parametrize('action',['ready','update','handover'])
def test_work_actions_require_details(monkeypatch,signed_in,action):
    result=client.post('/api/v1/engineering/casepacker-requests/7/actions',json={'action':action,'note':' '})
    assert result.status_code==422


def test_write_requires_login():
    assert client.post('/api/v1/engineering/casepacker-requests/7/actions',json={'action':'accept'}).status_code==401


def test_conflicting_engineer_action_returns_safe_conflict(monkeypatch,signed_in):
    def conflict(*a,**k): raise PulseCaptureError(409,'Already ready.')
    monkeypatch.setattr(eng,'update_casepacker_request',conflict)
    result=client.post('/api/v1/engineering/casepacker-requests/7/actions',json={'action':'ready','note':'Checked'})
    assert result.status_code==409
    assert result.json()['detail']=='Already ready.'


def test_tablet_status_reports_no_request_without_fabricating_job(monkeypatch):
    monkeypatch.setattr(capture,'get_casepacker_requests',lambda id: [])
    assert client.get('/api/v1/line-stoppages/11/casepacker').json()=={'request':None}
