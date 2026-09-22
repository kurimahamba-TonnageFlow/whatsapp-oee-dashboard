# ==========================================================
# TONNAGEFLOW PULSE
# Engineering API
# ==========================================================
#
# HTTP-only. Every route except /login (and /logout, which only
# requires *a* bearer token to revoke) depends on
# engineering_auth.require_engineering_session, which returns the
# engineer_name recorded at login - used as the authenticated actor
# for every write. The engineer identity NEVER comes from the request
# body; any engineer_name/engineer field in a request would be
# ignored even if a caller sent one, because none of the request
# models below declare such a field.
#
# Deliberately separate from src/management_api.py: a different auth
# module (engineering_auth, not management_auth), a different PIN
# (ENGINEERING_PIN), and no access to any /api/v1/management/* route
# or vice versa. No CLI input functions are called from this module.

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from . import engineering_auth
    from .database import (
        accept_engineering_fault,
        add_engineering_repair_update,
        close_engineering_fault,
        get_downtime_event_by_id,
        get_engineering_faults,
        hand_over_engineering_fault,
    )
    from .domain_constants import ENGINEERS
except ImportError:
    import engineering_auth
    from database import (
        accept_engineering_fault,
        add_engineering_repair_update,
        close_engineering_fault,
        get_downtime_event_by_id,
        get_engineering_faults,
        hand_over_engineering_fault,
    )
    from domain_constants import ENGINEERS


router = APIRouter(prefix="/api/v1/engineering", tags=["engineering"])

MAX_TEXT_LENGTH = 2000
MAX_SHORT_FIELD_LENGTH = 200
MAX_REASON_LENGTH = 500

REPAIR_CLASSIFICATIONS = ("Mechanical", "Machine Setting")

_SETTING_FIELD_NAMES = (
    "setting_name",
    "previous_value",
    "new_value",
    "reason_for_change",
    "affected_products_or_formats",
)


# ==========================================================
# SAFE DB HELPER
# ==========================================================


def _safe_db_call(operation_name, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)

    except Exception:
        print("DATABASE ERROR")
        print(f"Engineering operation failed: {operation_name}")

        raise HTTPException(
            status_code=503,
            detail="Could not complete the request. Please try again.",
        )


def _server_timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================


class EngineeringLoginRequest(BaseModel):
    pin: str
    engineer_name: str

    @field_validator("engineer_name")
    @classmethod
    def known_engineer(cls, value):
        stripped = value.strip()

        if stripped not in ENGINEERS:
            raise ValueError("Engineer name is not recognised.")

        return stripped


class EngineeringLoginResponse(BaseModel):
    status: str
    token: str
    engineer_name: str
    expires_at: datetime


@router.post("/login", response_model=EngineeringLoginResponse)
def login(payload: EngineeringLoginRequest, request: Request):
    if not engineering_auth.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Engineering login is not configured.",
        )

    client_key = request.client.host if request.client else "unknown"

    if engineering_auth.is_locked_out(client_key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later.",
        )

    if not engineering_auth.check_pin(payload.pin):
        engineering_auth.record_failed_attempt(client_key)

        raise HTTPException(status_code=401, detail="Incorrect PIN.")

    engineering_auth.clear_failed_attempts(client_key)
    session = engineering_auth.create_session(payload.engineer_name)

    return EngineeringLoginResponse(
        status="success",
        token=session["token"],
        engineer_name=payload.engineer_name,
        expires_at=session["expires_at"],
    )


@router.post("/logout")
def logout(token: str = Depends(engineering_auth.get_bearer_token)):
    engineering_auth.revoke_session(token)

    return {"status": "success", "message": "Logged out."}


# ==========================================================
# FAULT LISTING
# ==========================================================


class EngineeringFaultRepairUpdate(BaseModel):
    id: int
    engineer: str | None
    update_type: str
    repair_classification: str | None
    finding: str | None
    action: str | None
    notes: str | None
    setting_name: str | None
    previous_value: str | None
    new_value: str | None
    reason_for_change: str | None
    affected_products_or_formats: str | None
    engineering_status: str
    # Required, not Optional: a verified live-schema preflight (see
    # migrations/0002_engineering_workflow.sql) confirmed
    # engineering_updates.created_at is NOT NULL DEFAULT now() for
    # every row already in the table, historical or new - there is no
    # such thing as a repair update with an unknown creation time in
    # this database, so this field never fabricates a fallback and
    # never needs to tolerate null.
    created_at: datetime


class EngineeringFault(BaseModel):
    downtime_event_id: int
    production_run_id: int
    production_line: str
    fault_id: int
    machine: str
    reason: str
    reported_by: str
    engineer: str | None
    production_status: str
    engineering_status: str
    opened_at: datetime
    accepted_at: datetime | None
    resolved_at: datetime | None
    duration_minutes: float
    duration_is_active: bool
    repair_updates: list[EngineeringFaultRepairUpdate]


class EngineeringFaultsResponse(BaseModel):
    items: list[EngineeringFault]
    total: int


def engineering_fault_filters(
    production_line: str | None = Query(default=None),
    machine: str | None = Query(default=None),
    engineer: str | None = Query(default=None),
    fault_status: str | None = Query(default=None),
) -> dict:
    return {
        "production_line": production_line,
        "machine": machine,
        "engineer": engineer,
        "fault_status": fault_status,
    }


@router.get("/faults", response_model=EngineeringFaultsResponse)
def list_faults(
    filters: dict = Depends(engineering_fault_filters),
    engineer_name: str = Depends(engineering_auth.require_engineering_session),
):
    rows = _safe_db_call("get_engineering_faults", get_engineering_faults, filters)
    items = [EngineeringFault(**row) for row in rows]

    return EngineeringFaultsResponse(items=items, total=len(items))


# ==========================================================
# SHARED FAULT LOOKUP / OWNERSHIP CHECK
# ==========================================================


def _get_fault_or_404(downtime_event_id):
    fault = _safe_db_call(
        "get_downtime_event_by_id", get_downtime_event_by_id, downtime_event_id
    )

    if fault is None:
        raise HTTPException(
            status_code=404, detail=f"Fault {downtime_event_id} was not found."
        )

    return fault


def _load_owned_open_fault(downtime_event_id, engineer_name):
    """Shared existence/status/ownership check for /updates and
    /close: the fault must exist, still be Ongoing, and be accepted by
    the calling engineer specifically (not unassigned, not someone
    else's)."""
    fault = _get_fault_or_404(downtime_event_id)

    if fault["production_status"] != "Ongoing":
        raise HTTPException(
            status_code=409,
            detail=f"Fault {downtime_event_id} is already resolved.",
        )

    if fault["engineer"] != engineer_name:
        raise HTTPException(
            status_code=409,
            detail="This job is not accepted by you. Accept it before adding an update.",
        )

    return fault


# ==========================================================
# ACCEPT / START WORK
# ==========================================================


class EngineeringAcceptResponse(BaseModel):
    status: str
    downtime_event_id: int
    engineer: str
    engineering_status: str
    accepted_at: datetime | None


@router.post("/faults/{downtime_event_id}/accept", response_model=EngineeringAcceptResponse)
def accept_fault(
    downtime_event_id: int,
    engineer_name: str = Depends(engineering_auth.require_engineering_session),
):
    existing = _get_fault_or_404(downtime_event_id)

    if existing["production_status"] != "Ongoing":
        raise HTTPException(
            status_code=409,
            detail=f"Fault {downtime_event_id} is already resolved.",
        )

    accepted = _safe_db_call(
        "accept_engineering_fault",
        accept_engineering_fault,
        downtime_event_id,
        engineer_name,
        _server_timestamp(),
    )

    if accepted is None:
        # The guarded UPDATE matched zero rows: either the fault was
        # resolved a moment ago, or another engineer already holds it.
        # A fresh lookup distinguishes the two for an accurate message -
        # same idiom as management_api.force_close_run().
        current = _safe_db_call(
            "get_downtime_event_by_id", get_downtime_event_by_id, downtime_event_id
        )

        if current is not None and current["production_status"] != "Ongoing":
            raise HTTPException(
                status_code=409,
                detail=f"Fault {downtime_event_id} is already resolved.",
            )

        raise HTTPException(
            status_code=409,
            detail=f"Fault {downtime_event_id} has already been accepted by another engineer.",
        )

    return EngineeringAcceptResponse(
        status="success",
        downtime_event_id=accepted["id"],
        engineer=accepted["engineer"],
        engineering_status=accepted["engineering_status"],
        accepted_at=accepted["accepted_at"],
    )


# ==========================================================
# REPAIR UPDATE PAYLOAD (shared by /updates and /close)
# ==========================================================


class RepairUpdateRequest(BaseModel):
    classification: Literal["Mechanical", "Machine Setting"]
    finding: str = Field(max_length=MAX_TEXT_LENGTH)
    action: str = Field(max_length=MAX_TEXT_LENGTH)
    notes: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    setting_name: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    previous_value: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    new_value: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LENGTH)
    reason_for_change: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)
    affected_products_or_formats: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)

    @field_validator("finding", "action")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("This field cannot be blank.")

        return stripped

    @field_validator(
        "notes",
        "setting_name",
        "previous_value",
        "new_value",
        "reason_for_change",
        "affected_products_or_formats",
    )
    @classmethod
    def trim_optional(cls, value):
        if value is None:
            return None

        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def classification_fields(self):
        setting_values = {name: getattr(self, name) for name in _SETTING_FIELD_NAMES}

        if self.classification == "Machine Setting":
            missing = [name for name, value in setting_values.items() if not value]

            if missing:
                raise ValueError(
                    "Machine Setting updates require: "
                    + ", ".join(_SETTING_FIELD_NAMES)
                    + "."
                )

        else:
            provided = [name for name, value in setting_values.items() if value]

            if provided:
                raise ValueError(
                    "Mechanical updates must not include Machine Setting fields: "
                    + ", ".join(provided)
                    + "."
                )

        return self


# ==========================================================
# REPAIR UPDATES (interim)
# ==========================================================


class EngineeringUpdateResponse(BaseModel):
    status: str
    downtime_event_id: int
    engineering_update_id: int
    created_at: datetime


@router.post(
    "/faults/{downtime_event_id}/updates", response_model=EngineeringUpdateResponse
)
def add_update(
    downtime_event_id: int,
    payload: RepairUpdateRequest,
    engineer_name: str = Depends(engineering_auth.require_engineering_session),
):
    fault = _load_owned_open_fault(downtime_event_id, engineer_name)

    repair_update = {
        "production_run_id": fault["production_run_id"],
        "fault_id": fault["fault_id"],
        "engineer": engineer_name,
        "repair_classification": payload.classification,
        "finding": payload.finding,
        "action": payload.action,
        "notes": payload.notes,
        "setting_name": payload.setting_name,
        "previous_value": payload.previous_value,
        "new_value": payload.new_value,
        "reason_for_change": payload.reason_for_change,
        "affected_products_or_formats": payload.affected_products_or_formats,
    }

    created = _safe_db_call(
        "add_engineering_repair_update",
        add_engineering_repair_update,
        downtime_event_id,
        repair_update,
    )

    return EngineeringUpdateResponse(
        status="success",
        downtime_event_id=downtime_event_id,
        engineering_update_id=created["id"],
        created_at=created["created_at"],
    )


# ==========================================================
# CLOSE FAULT
# ==========================================================


class EngineeringCloseResponse(BaseModel):
    status: str
    downtime_event_id: int
    engineer: str | None
    engineering_status: str
    production_status: str
    resolved_at: datetime | None


@router.post("/faults/{downtime_event_id}/close", response_model=EngineeringCloseResponse)
def close_fault(
    downtime_event_id: int,
    payload: RepairUpdateRequest,
    engineer_name: str = Depends(engineering_auth.require_engineering_session),
):
    fault = _load_owned_open_fault(downtime_event_id, engineer_name)

    repair_update = {
        "production_run_id": fault["production_run_id"],
        "fault_id": fault["fault_id"],
        "engineer": engineer_name,
        "repair_classification": payload.classification,
        "finding": payload.finding,
        "action": payload.action,
        "notes": payload.notes,
        "setting_name": payload.setting_name,
        "previous_value": payload.previous_value,
        "new_value": payload.new_value,
        "reason_for_change": payload.reason_for_change,
        "affected_products_or_formats": payload.affected_products_or_formats,
    }

    closed = _safe_db_call(
        "close_engineering_fault",
        close_engineering_fault,
        downtime_event_id,
        repair_update,
        _server_timestamp(),
    )

    if closed is None:
        raise HTTPException(
            status_code=409,
            detail=f"Fault {downtime_event_id} was already resolved by someone else.",
        )

    return EngineeringCloseResponse(
        status="success",
        downtime_event_id=closed["id"],
        engineer=closed["engineer"],
        engineering_status=closed["engineering_status"],
        production_status=closed["production_status"],
        resolved_at=closed["resolved_at"],
    )


# ==========================================================
# HAND OVER JOB
# ==========================================================
#
# Releases an owned, still-open fault back to unassigned so a different
# engineer can accept it - this endpoint never assigns it to anyone
# else directly. The handover note is recorded as a 'Follow Up'
# engineering_updates row (the only currently-permitted update_type
# that fits an interim, non-final event - see chk_engineering_update_type
# in migrations/0002_engineering_workflow.sql) using the existing
# `finding` column for the note itself and a fixed `action` describing
# what happened; `repair_classification` is left NULL, which is how the
# fault-listing UI tells a handover apart from an ordinary repair
# update in the history.

MAX_HANDOVER_NOTE_LENGTH = MAX_REASON_LENGTH

HANDOVER_ACTION_TEXT = (
    "Job handed over; engineer unassigned and fault returned to Open Production Faults."
)


class HandoverRequest(BaseModel):
    note: str = Field(max_length=MAX_HANDOVER_NOTE_LENGTH)

    @field_validator("note")
    @classmethod
    def not_blank(cls, value):
        stripped = value.strip()

        if not stripped:
            raise ValueError("A handover note is required.")

        return stripped


class EngineeringHandoverResponse(BaseModel):
    status: str
    downtime_event_id: int
    engineer: str | None
    engineering_status: str
    production_status: str
    accepted_at: datetime | None


@router.post(
    "/faults/{downtime_event_id}/handover", response_model=EngineeringHandoverResponse
)
def handover_fault(
    downtime_event_id: int,
    payload: HandoverRequest,
    engineer_name: str = Depends(engineering_auth.require_engineering_session),
):
    fault = _load_owned_open_fault(downtime_event_id, engineer_name)

    handover = {
        "production_run_id": fault["production_run_id"],
        "fault_id": fault["fault_id"],
        "engineer": engineer_name,
        "finding": payload.note,
        "action": HANDOVER_ACTION_TEXT,
    }

    released = _safe_db_call(
        "hand_over_engineering_fault",
        hand_over_engineering_fault,
        downtime_event_id,
        handover,
    )

    if released is None:
        # The guarded UPDATE matched zero rows: the fault was resolved,
        # or is no longer assigned to this engineer, since the pre-check
        # above ran - a racing close/accept/handover committed first.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Fault {downtime_event_id} is no longer assigned to you, "
                "or has already been resolved."
            ),
        )

    return EngineeringHandoverResponse(
        status="success",
        downtime_event_id=released["id"],
        engineer=released["engineer"],
        engineering_status=released["engineering_status"],
        production_status=released["production_status"],
        accepted_at=released["accepted_at"],
    )
