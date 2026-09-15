# ==========================================================
# TONNAGEFLOW PULSE
# Management API
# ==========================================================
#
# HTTP-only. Every route except /login (and /logout, which only
# requires *a* bearer token to revoke) depends on
# management_auth.require_management_session, which returns the
# manager_name recorded at login - used for the audit trail on every
# write. No CLI input functions are called from this module.

from datetime import date, datetime, timedelta, timezone
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator, field_validator

try:
    from . import management_auth
    from .database import (
        create_button,
        create_machine,
        create_production_line,
        force_close_production_run,
        get_all_active_runs,
        get_button,
        get_machine,
        get_production_line,
        get_production_run_by_id,
        get_technician_performance,
        insert_audit_log,
        list_buttons,
        list_machines,
        list_production_lines,
        update_button,
        update_machine,
        update_production_line,
    )
except ImportError:
    import management_auth
    from database import (
        create_button,
        create_machine,
        create_production_line,
        force_close_production_run,
        get_all_active_runs,
        get_button,
        get_machine,
        get_production_line,
        get_production_run_by_id,
        get_technician_performance,
        insert_audit_log,
        list_buttons,
        list_machines,
        list_production_lines,
        update_button,
        update_machine,
        update_production_line,
    )


router = APIRouter(prefix="/api/v1/management", tags=["management"])

MIN_SAMPLE_RUNS = int(os.getenv("MANAGEMENT_MIN_SAMPLE_RUNS", "3"))

FORCE_CLOSE_REASONS = [
    "Technician left mid-shift",
    "Tablet or browser closed",
    "Run started by mistake",
    "Changeover completed",
    "Production stopped",
    "Duplicate run",
    "Other",
]


# ==========================================================
# SAFE DB / AUDIT HELPERS
# ==========================================================


def _safe_db_call(operation_name, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)

    except Exception:
        print("DATABASE ERROR")
        print(f"Management operation failed: {operation_name}")

        raise HTTPException(
            status_code=503,
            detail="Could not complete the request. Please try again.",
        )


def _jsonable(value):
    if value is None:
        return None

    result = {}
    for key, val in value.items():
        result[key] = val.isoformat() if hasattr(val, "isoformat") else val

    return result


def _write_audit(action, manager_name, record_type, record_id, previous_value=None, new_value=None, reason=None):
    try:
        insert_audit_log(
            action=action,
            manager_name=manager_name,
            record_type=record_type,
            record_id=record_id,
            previous_value=_jsonable(previous_value),
            new_value=_jsonable(new_value),
            reason=reason,
        )

    except Exception:
        # The primary operation already committed - an audit-log write
        # failure must not undo or fail it, just be reported safely.
        print("DATABASE ERROR")
        print(f"Could not write audit log for action: {action}")


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================


class LoginRequest(BaseModel):
    pin: str
    manager_name: str

    @field_validator("manager_name")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("Manager name cannot be blank.")

        return stripped


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    if not management_auth.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Management login is not configured.",
        )

    client_key = request.client.host if request.client else "unknown"

    if management_auth.is_locked_out(client_key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later.",
        )

    if not management_auth.check_pin(payload.pin):
        management_auth.record_failed_attempt(client_key)

        raise HTTPException(status_code=401, detail="Incorrect PIN.")

    management_auth.clear_failed_attempts(client_key)
    session = management_auth.create_session(payload.manager_name)

    return {
        "status": "success",
        "token": session["token"],
        "manager_name": payload.manager_name,
        "expires_at": session["expires_at"],
    }


@router.post("/logout")
def logout(token: str = Depends(management_auth.get_bearer_token)):
    management_auth.revoke_session(token)

    return {"status": "success", "message": "Logged out."}


# ==========================================================
# PRODUCTION LINES
# ==========================================================


class LineCreateRequest(BaseModel):
    name: str
    display_order: int = 0

    @field_validator("name")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("Line name cannot be blank.")

        return stripped


class LineUpdateRequest(BaseModel):
    name: str | None = None
    active: bool | None = None
    display_order: int | None = None


@router.get("/lines")
def list_lines(manager_name: str = Depends(management_auth.require_management_session)):
    return {"items": _safe_db_call("list_production_lines", list_production_lines)}


@router.post("/lines", status_code=201)
def create_line(
    payload: LineCreateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    created = _safe_db_call(
        "create_production_line",
        create_production_line,
        payload.name,
        payload.display_order,
    )

    _write_audit("create_line", manager_name, "production_line", created["id"], None, created)

    return created


@router.patch("/lines/{line_id}")
def patch_line(
    line_id: int,
    payload: LineUpdateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    before = _safe_db_call("get_production_line", get_production_line, line_id)

    if before is None:
        raise HTTPException(status_code=404, detail=f"Production Line {line_id} was not found.")

    updated = _safe_db_call(
        "update_production_line",
        update_production_line,
        line_id,
        payload.name,
        payload.active,
        payload.display_order,
    )

    _write_audit("update_line", manager_name, "production_line", line_id, before, updated)

    return updated


# ==========================================================
# MACHINES / SECTIONS
# ==========================================================


class MachineCreateRequest(BaseModel):
    name: str
    display_order: int = 0

    @field_validator("name")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("Machine name cannot be blank.")

        return stripped


class MachineUpdateRequest(BaseModel):
    name: str | None = None
    active: bool | None = None
    display_order: int | None = None


@router.get("/lines/{line_id}/machines")
def list_line_machines(
    line_id: int,
    manager_name: str = Depends(management_auth.require_management_session),
):
    return {"items": _safe_db_call("list_machines", list_machines, line_id)}


@router.post("/lines/{line_id}/machines", status_code=201)
def create_line_machine(
    line_id: int,
    payload: MachineCreateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    created = _safe_db_call(
        "create_machine", create_machine, line_id, payload.name, payload.display_order
    )

    _write_audit("create_machine", manager_name, "machine", created["id"], None, created)

    return created


@router.patch("/machines/{machine_id}")
def patch_machine(
    machine_id: int,
    payload: MachineUpdateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    before = _safe_db_call("get_machine", get_machine, machine_id)

    if before is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} was not found.")

    updated = _safe_db_call(
        "update_machine",
        update_machine,
        machine_id,
        payload.name,
        payload.active,
        payload.display_order,
    )

    _write_audit("update_machine", manager_name, "machine", machine_id, before, updated)

    return updated


# ==========================================================
# FAULT / PLANNED-DOWNTIME BUTTONS
# ==========================================================


class ButtonCreateRequest(BaseModel):
    name: str
    event_type: str
    ownership: str
    fault_category: str | None = None
    display_order: int = 0

    @field_validator("name")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("Button name cannot be blank.")

        return stripped

    @field_validator("event_type")
    @classmethod
    def known_event_type(cls, value):
        if value not in ("planned_downtime", "unplanned_fault"):
            raise ValueError("event_type must be 'planned_downtime' or 'unplanned_fault'.")

        return value

    @field_validator("ownership")
    @classmethod
    def known_ownership(cls, value):
        if value not in ("Production", "Engineering"):
            raise ValueError("ownership must be 'Production' or 'Engineering'.")

        return value


class ButtonUpdateRequest(BaseModel):
    name: str | None = None
    event_type: str | None = None
    ownership: str | None = None
    fault_category: str | None = None
    display_order: int | None = None
    active: bool | None = None


@router.get("/machines/{machine_id}/buttons")
def list_machine_buttons(
    machine_id: int,
    manager_name: str = Depends(management_auth.require_management_session),
):
    return {"items": _safe_db_call("list_buttons", list_buttons, machine_id)}


@router.post("/machines/{machine_id}/buttons", status_code=201)
def create_machine_button(
    machine_id: int,
    payload: ButtonCreateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    created = _safe_db_call(
        "create_button",
        create_button,
        machine_id,
        payload.name,
        payload.event_type,
        payload.ownership,
        payload.fault_category,
        payload.display_order,
    )

    _write_audit("create_button", manager_name, "button", created["id"], None, created)

    return created


@router.patch("/buttons/{button_id}")
def patch_button(
    button_id: int,
    payload: ButtonUpdateRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    before = _safe_db_call("get_button", get_button, button_id)

    if before is None:
        raise HTTPException(status_code=404, detail=f"Button {button_id} was not found.")

    updated = _safe_db_call(
        "update_button",
        update_button,
        button_id,
        payload.name,
        payload.event_type,
        payload.ownership,
        payload.fault_category,
        payload.display_order,
        payload.active,
    )

    _write_audit("update_button", manager_name, "button", button_id, before, updated)

    return updated


# ==========================================================
# ACTIVE RUNS + FORCE CLOSE
# ==========================================================


class ForceCloseRequest(BaseModel):
    reason: str
    note: str | None = None

    @field_validator("reason")
    @classmethod
    def known_reason(cls, value):
        if value not in FORCE_CLOSE_REASONS:
            raise ValueError(f"reason must be one of {FORCE_CLOSE_REASONS}.")

        return value

    @model_validator(mode="after")
    def note_required_for_other(self):
        if self.reason == "Other" and not (self.note and self.note.strip()):
            raise ValueError("note is required when reason is 'Other'.")

        return self


@router.get("/active-runs")
def active_runs(manager_name: str = Depends(management_auth.require_management_session)):
    runs = _safe_db_call("get_all_active_runs", get_all_active_runs)
    now = datetime.now(timezone.utc)

    items = []
    for run in runs:
        items.append({**run, "active_seconds": (now - run["started_at"]).total_seconds()})

    return {"items": items}


@router.post("/runs/{run_id}/force-close")
def force_close_run(
    run_id: int,
    payload: ForceCloseRequest,
    manager_name: str = Depends(management_auth.require_management_session),
):
    before = _safe_db_call("get_production_run_by_id", get_production_run_by_id, run_id)

    if before is None:
        raise HTTPException(status_code=404, detail=f"Production Run {run_id} was not found.")

    if before["status"] != "Active":
        raise HTTPException(
            status_code=409,
            detail=f"Production Run {run_id} is not Active (current status: {before['status']}).",
        )

    finished_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    closed = _safe_db_call(
        "force_close_production_run", force_close_production_run, run_id, finished_at
    )

    if closed is None:
        # The partial unique index + WHERE status='Active' already
        # prevented a double-close; someone else closed/changed it
        # between our check above and this update.
        raise HTTPException(
            status_code=409,
            detail=f"Production Run {run_id} was already closed by someone else.",
        )

    reason_text = payload.reason if payload.reason != "Other" else f"Other: {payload.note}"

    _write_audit(
        "force_close_run",
        manager_name,
        "production_run",
        run_id,
        before,
        closed,
        reason=reason_text,
    )

    return {
        "status": "success",
        "run_id": closed["id"],
        "production_line": closed["production_line"],
        "run_status": closed["status"],
        "closed_by": manager_name,
        "reason": reason_text,
    }


# ==========================================================
# TECHNICIAN PERFORMANCE
# ==========================================================


def _quarter_bounds(year, quarter):
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)

    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date(year, start_month + 3, 1) - timedelta(days=1)

    return start, end


def resolve_period(period, date_from, date_to):
    """Named presets resolve to whole calendar-period bounds (e.g.
    'current_week' = Monday-Sunday of this week), not "period to date" -
    a documented, consistent convention rather than a guessed one."""
    if not period or period == "custom":
        return date_from, date_to

    today = date.today()

    if period == "today":
        return today, today

    if period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    if period == "current_week":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)

    if period == "previous_week":
        this_monday = today - timedelta(days=today.weekday())
        previous_monday = this_monday - timedelta(days=7)
        return previous_monday, previous_monday + timedelta(days=6)

    if period == "current_month":
        start = today.replace(day=1)
        next_month = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)

    if period == "previous_month":
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        return end.replace(day=1), end

    if period == "current_quarter":
        quarter = (today.month - 1) // 3 + 1
        return _quarter_bounds(today.year, quarter)

    if period == "previous_quarter":
        quarter = (today.month - 1) // 3 + 1
        if quarter == 1:
            return _quarter_bounds(today.year - 1, 4)
        return _quarter_bounds(today.year, quarter - 1)

    if period == "current_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)

    raise HTTPException(status_code=422, detail=f"Unknown period '{period}'.")


def _classify(target_achievement_percent):
    if target_achievement_percent is None:
        return "Insufficient data"

    if target_achievement_percent >= 95:
        return "On target"

    if target_achievement_percent >= 80:
        return "At risk"

    return "Needs review"


@router.get("/technician-performance")
def technician_performance(
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    production_line: str | None = None,
    shift: str | None = None,
    technician: str | None = None,
    product: str | None = None,
    customer: str | None = None,
    manager_name: str = Depends(management_auth.require_management_session),
):
    resolved_from, resolved_to = resolve_period(period, date_from, date_to)

    filters = {
        "date_from": resolved_from,
        "date_to": resolved_to,
        "production_line": production_line,
        "shift": shift,
        "technician": technician,
        "product": product,
        "customer": customer,
        "run_status": "Completed",
    }

    results = _safe_db_call("get_technician_performance", get_technician_performance, filters)

    ranked = []
    insufficient_data = []

    for entry in results:
        if entry["completed_runs"] < MIN_SAMPLE_RUNS:
            # Too few runs to trust the percentage either way - always
            # "Insufficient data", regardless of what the percentage is.
            entry["label"] = "Insufficient data"
            insufficient_data.append(entry)
        else:
            entry["label"] = _classify(entry["target_achievement_percent"])
            ranked.append(entry)

    ranked.sort(
        key=lambda e: (
            e["target_achievement_percent"] is None,
            -(e["target_achievement_percent"] or 0),
        )
    )

    return {
        "period": period or "custom",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "minimum_sample_size": MIN_SAMPLE_RUNS,
        "ranked": ranked,
        "insufficient_data": insufficient_data,
    }
