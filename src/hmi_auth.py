"""Tablet access boundary. One API worker; operator names remain reported identities."""
import os
import hmac
import secrets
import threading
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from . import management_auth

router = APIRouter(prefix="/api/v1/hmi-access", tags=["tablet access"])
_sessions = {}
_attempts = {}
_lock = threading.Lock()

class Login(BaseModel):
    pin: str = Field(min_length=1, max_length=200)
    device_name: str = Field(min_length=1, max_length=100)

@router.post("/login")
def login(payload: Login, request: Request):
    pin = os.getenv("HMI_DEVICE_PIN")
    if not pin:
        raise HTTPException(503, "Tablet access is not configured. Contact Management.")
    now = datetime.now(timezone.utc)
    client = request.client.host if request.client else "unknown"
    with _lock:
        failures, expiry = _attempts.get(client, (0, now))
        if expiry <= now:
            failures = 0
        if failures >= 5:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
        if not hmac.compare_digest(payload.pin.encode(), pin.encode()):
            _attempts[client] = (failures + 1, now + timedelta(minutes=15))
            raise HTTPException(401, "Tablet PIN not recognised.")
        if not payload.device_name.strip():
            raise HTTPException(422, "Enter a tablet name.")
        _attempts.pop(client, None)
        # Bound expired-session retention on each successful sign-in.
        for old in list(_sessions):
            if _sessions[old]["expires_at"] <= now:
                _sessions.pop(old)
        token = secrets.token_urlsafe(32)
        _sessions[token] = {"device_name": payload.device_name.strip(), "expires_at": now + timedelta(hours=12)}
        return {"token": token, **_sessions[token]}

def require_device(x_hmi_session: str | None = Header(default=None)):
    with _lock:
        session = _sessions.get(x_hmi_session)
        if not session or session["expires_at"] <= datetime.now(timezone.utc):
            _sessions.pop(x_hmi_session, None)
            raise HTTPException(401, "Tablet sign-in required.")
        return dict(session)

def require_hmi_access(x_hmi_session: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    # Management actions in the shared capture router retain their own role guards.
    if authorization and authorization.startswith("Bearer "):
        manager = management_auth.get_session(authorization[7:])
        if manager:
            return {"device_name": "Management: " + manager["manager_name"]}
    return require_device(x_hmi_session)

@router.get("/session")
def session(device=Depends(require_device)):
    return device

@router.post("/logout")
def logout(x_hmi_session: str | None = Header(default=None)):
    with _lock:
        _sessions.pop(x_hmi_session, None)
    return {"status": "signed_out"}
