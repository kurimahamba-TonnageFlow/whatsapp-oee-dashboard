# ==========================================================
# TONNAGEFLOW PULSE
# Management Authentication
# ==========================================================
#
# Server-side only. The Management PIN lives in MANAGEMENT_PIN (an
# environment variable, never committed) and is never sent to or
# stored in browser JavaScript. Sessions and login rate-limiting are
# in-memory (matching the existing per-line lock pattern in
# src/runs_api.py) - they reset on process restart and are not shared
# across multiple worker processes. That matches this project's
# existing single-process assumption; documented, not hidden.

from datetime import datetime, timedelta, timezone
import hmac
import os
import secrets
import threading

from fastapi import Depends, Header, HTTPException

MANAGEMENT_PIN = os.getenv("MANAGEMENT_PIN")

SESSION_MINUTES = int(os.getenv("MANAGEMENT_SESSION_MINUTES", "30"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("MANAGEMENT_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("MANAGEMENT_LOGIN_LOCKOUT_MINUTES", "15"))


# ==========================================================
# SESSIONS
# ==========================================================

_sessions = {}
_sessions_guard = threading.Lock()


def is_configured():
    return bool(MANAGEMENT_PIN)


def check_pin(pin):
    if not MANAGEMENT_PIN:
        return False

    return hmac.compare_digest(pin, MANAGEMENT_PIN)


def create_session(manager_name):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES)

    with _sessions_guard:
        _sessions[token] = {
            "manager_name": manager_name,
            "expires_at": expires_at,
        }

    return {"token": token, "expires_at": expires_at}


def get_session(token):
    with _sessions_guard:
        session = _sessions.get(token)

        if session is None:
            return None

        if session["expires_at"] <= datetime.now(timezone.utc):
            _sessions.pop(token, None)
            return None

        return session


def revoke_session(token):
    with _sessions_guard:
        _sessions.pop(token, None)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Management session required.",
        )

    return authorization[len("Bearer "):].strip()


def require_management_session(token: str = Depends(get_bearer_token)) -> str:
    """FastAPI dependency: validates the Bearer token, returns the
    manager_name recorded at login."""
    session = get_session(token)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Management session is invalid or has expired.",
        )

    return session["manager_name"]


# ==========================================================
# LOGIN RATE LIMITING / LOCKOUT
# ==========================================================

_login_attempts = {}
_login_attempts_guard = threading.Lock()


def is_locked_out(client_key):
    with _login_attempts_guard:
        record = _login_attempts.get(client_key)

        if record is None:
            return False

        locked_until = record.get("locked_until")
        return locked_until is not None and locked_until > datetime.now(timezone.utc)


def record_failed_attempt(client_key):
    with _login_attempts_guard:
        record = _login_attempts.setdefault(
            client_key, {"failures": 0, "locked_until": None}
        )
        record["failures"] += 1

        if record["failures"] >= LOGIN_MAX_ATTEMPTS:
            record["locked_until"] = (
                datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            )


def clear_failed_attempts(client_key):
    with _login_attempts_guard:
        _login_attempts.pop(client_key, None)
