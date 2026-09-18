# ==========================================================
# TONNAGEFLOW PULSE
# Engineering Authentication
# ==========================================================
#
# Server-side only. Deliberately mirrors src/management_auth.py's
# proven pattern (PIN via env var, HMAC-safe compare, in-memory
# bearer-token sessions, login lockout) but is a fully separate
# module with its own module-level state:
#   - ENGINEERING_PIN, not MANAGEMENT_PIN.
#   - Its own _sessions dict/lock - an Engineering token is looked up
#     only here, so it is structurally impossible for it to validate
#     against management_auth.require_management_session, and vice
#     versa. Neither module imports or shares the other's state.
#   - Its own _login_attempts dict/lock - Engineering lockouts never
#     affect Management logins or the reverse.
#
# Sessions and login rate-limiting are in-memory - they reset on
# process restart and are not shared across multiple worker processes.
# Matches management_auth.py's existing, documented single-process
# assumption for this project.

from datetime import datetime, timedelta, timezone
import hmac
import os
import secrets
import threading

from fastapi import Depends, Header, HTTPException

ENGINEERING_PIN = os.getenv("ENGINEERING_PIN")

SESSION_MINUTES = int(os.getenv("ENGINEERING_SESSION_MINUTES", "30"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("ENGINEERING_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("ENGINEERING_LOGIN_LOCKOUT_MINUTES", "15"))


# ==========================================================
# SESSIONS
# ==========================================================

_sessions = {}
_sessions_guard = threading.Lock()


def is_configured():
    return bool(ENGINEERING_PIN)


def check_pin(pin):
    if not ENGINEERING_PIN:
        return False

    return hmac.compare_digest(pin, ENGINEERING_PIN)


def create_session(engineer_name):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SESSION_MINUTES)

    with _sessions_guard:
        _sessions[token] = {
            "engineer_name": engineer_name,
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
            detail="Engineering session required.",
        )

    return authorization[len("Bearer "):].strip()


def require_engineering_session(token: str = Depends(get_bearer_token)) -> str:
    """FastAPI dependency: validates the Bearer token against this
    module's own session store only, returns the engineer_name
    recorded at login. A Management token is never found here (it
    lives in management_auth._sessions, a different dict), so it is
    always rejected with 401 - same in reverse for
    management_auth.require_management_session."""
    session = get_session(token)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Engineering session is invalid or has expired.",
        )

    return session["engineer_name"]


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
