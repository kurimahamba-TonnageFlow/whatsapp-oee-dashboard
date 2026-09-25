# ==========================================================
# TONNAGEFLOW PULSE
# HMI capture API (Stage 6B1 / 6B2)
# ==========================================================
#
# The write side the React HMI calls. Same access model as
# POST /api/v1/runs: the factory-floor HMI is unauthenticated, and every
# request is validated against the known line/technician configuration
# and the run's live database state. The server clock is the only
# source of event timestamps.
#
# IDEMPOTENCY: every write requires an `Idempotency-Key` header - a
# client-generated key that stays the same for one logical action until
# it succeeds or is deliberately cancelled. The key is claimed in the
# SAME database transaction as the rows it creates, and the response is
# stored with it, so a double tap or a retry after a timeout returns the
# original response (header `Idempotent-Replayed: true`) instead of
# writing twice. Reusing a key with different details is a 409.
#
# Every manufacturing figure in a response is calculated by
# src/pulse_calculations.py - the HMI only displays it.

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from . import pulse_calculations as calc
    from .database import (
        IdempotencyRequest,
        IdempotentReplay,
        PulseCaptureError,
        complete_run_changeover,
        end_planned_downtime,
        get_completion_basis,
        get_hmi_run_state,
        get_open_changeover,
        get_production_run_by_id,
        record_hourly_update,
        record_xray_capture,
        report_fault_to_engineering,
        start_planned_downtime,
        start_run_changeover,
    )
    from .dashboard_reports import serialize_changeover
    from .main import line_technicians_by_line
except ImportError:
    import pulse_calculations as calc
    from database import (
        IdempotencyRequest,
        IdempotentReplay,
        PulseCaptureError,
        complete_run_changeover,
        end_planned_downtime,
        get_completion_basis,
        get_hmi_run_state,
        get_open_changeover,
        get_production_run_by_id,
        record_hourly_update,
        record_xray_capture,
        report_fault_to_engineering,
        start_planned_downtime,
        start_run_changeover,
    )
    from dashboard_reports import serialize_changeover
    from main import line_technicians_by_line


router = APIRouter(prefix="/api/v1", tags=["hmi-capture"])

MAX_PALLETS_PER_UPDATE = Decimal(1000)
MAX_XRAY_PACK_COUNT = 10_000_000
MAX_TEXT_LENGTH = 500
MAX_SHORT_TEXT_LENGTH = 120
CHANGEOVER_REASON = "Changeover"

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Client-generated key, identical for every retry of one logical action.",
    ),
]


def _now():
    return datetime.now(timezone.utc)


def safe_503():
    return HTTPException(status_code=503, detail="Could not save this to Pulse. Please try again.")


def _call(operation_name, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)

    except PulseCaptureError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    except Exception:
        print("DATABASE ERROR")
        print(f"HMI capture operation failed: {operation_name}")
        raise safe_503()


def build_idempotency(key, action, payload, status_code, to_body):
    """payload: the validated request model. The fingerprint covers the
    action (which includes the path id) and the full request body."""
    canonical = json.dumps(
        {"action": action, "payload": payload.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return IdempotencyRequest(
        key=key,
        action=action,
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        respond=lambda result: (status_code, jsonable_encoder(to_body(result))),
    )


def run_idempotent_write(operation_name, func, *args, idempotency):
    try:
        result = func(*args, idempotency=idempotency)

    except IdempotentReplay as replay:
        return JSONResponse(
            status_code=replay.status_code,
            content=replay.body,
            headers={"Idempotent-Replayed": "true"},
        )

    except PulseCaptureError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    except Exception:
        print("DATABASE ERROR")
        print(f"HMI capture operation failed: {operation_name}")
        raise safe_503()

    status_code, body = idempotency.respond(result)
    return JSONResponse(status_code=status_code, content=body)


def load_run(run_id):
    """Existence only. Whether the run is still Active is enforced inside
    each write's own transaction, AFTER its Idempotency-Key is checked -
    so a retry of an action that already completed the run still gets
    its original response instead of a misleading 409."""
    run = _call("get_production_run_by_id", get_production_run_by_id, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail=f"Production Run {run_id} was not found.")

    return run


def require_line_technician(production_line, technician):
    if technician not in line_technicians_by_line.get(production_line, []):
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{technician}' is not a known Line Technician for "
                f"Production Line '{production_line}'."
            ),
        )


def _require_known_technician(technician):
    known = {name for names in line_technicians_by_line.values() for name in names}
    if technician not in known:
        raise HTTPException(status_code=422, detail=f"'{technician}' is not a known Line Technician.")


def _require_known_line(production_line):
    if production_line not in line_technicians_by_line:
        raise HTTPException(
            status_code=422, detail=f"'{production_line}' is not a known Production Line."
        )


def strip_required(value):
    stripped = value.strip()
    if not stripped:
        raise ValueError("This field cannot be blank.")
    return stripped


def strip_optional(value):
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _pallets(value):
    return calc.as_number(value, calc.PALLETS_PLACES)


def _packs(value):
    return calc.as_number(value, calc.PACKS_PLACES)


def _minutes(value):
    return calc.as_number(value, calc.MINUTES_PLACES)


# ==========================================================
# HOURLY UPDATE
# ==========================================================


class HourlyUpdateRequest(BaseModel):
    line_technician: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    # Send as a string ("3.75") to keep exact decimal precision end to end.
    pallets_produced: Decimal = Field(ge=0, le=MAX_PALLETS_PER_UPDATE, decimal_places=4)
    other_loss_reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("line_technician")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("other_loss_reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)


def hourly_update_api(saved):
    config = saved["config"]
    expected = calc.to_decimal(saved["expected_packs"])
    actual = calc.to_decimal(saved["actual_packs"])

    return {
        "status": "success",
        "hourly_update_id": saved["hourly_update_id"],
        "production_run_id": saved["production_run_id"],
        "production_line": saved["production_line"],
        "shift": saved["shift"],
        "shift_window_start": saved["shift_window_start"],
        "period_started_at": saved["period_started_at"],
        "period_ended_at": saved["period_ended_at"],
        "period_minutes": _minutes(saved["period_minutes"]),
        "pallets_produced": _pallets(saved["actual_pallets"]),
        "expected_packs": _packs(expected),
        "expected_pallets": _pallets(saved["expected_pallets"]),
        "expected_tonnes": calc.as_number(config.packs_to_tonnes(expected), calc.TONNES_PLACES),
        "actual_packs": _packs(actual),
        "actual_tonnes": calc.as_number(config.packs_to_tonnes(actual), calc.TONNES_PLACES),
        "output_gap_packs": _packs(saved["estimated_lost_packs"]),
        "production_achievement_percent": calc.as_number(
            calc.percent(actual, expected), calc.PERCENT_PLACES
        ),
        "planned_downtime_minutes": _minutes(saved["planned_downtime_minutes"]),
        "pallets_remaining": _pallets(saved["pallets_remaining"]),
        "total_pallets_completed": _pallets(saved["total_pallets_completed"]),
        "potential_overrun_pallets": _pallets(saved["potential_overrun_pallets"]),
    }


@router.post("/runs/{run_id}/hourly-updates", status_code=201)
def submit_hourly_update(run_id: int, payload: HourlyUpdateRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)

    idempotency = build_idempotency(
        idempotency_key, f"hourly_update:{run_id}", payload, 201, hourly_update_api
    )

    return run_idempotent_write(
        "record_hourly_update",
        record_hourly_update,
        run_id,
        payload.pallets_produced,
        payload.line_technician,
        payload.other_loss_reason,
        _now(),
        idempotency=idempotency,
    )


# ==========================================================
# PLANNED DOWNTIME
# ==========================================================


class PlannedDowntimeStartRequest(BaseModel):
    reason: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    started_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)

    @field_validator("reason", "started_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("reason")
    @classmethod
    def not_changeover(cls, value):
        if value.lower() == CHANGEOVER_REASON.lower():
            raise ValueError(
                "Changeover is started with Start Changeover, which also records the "
                "new customer, product, pack weight and format."
            )
        return value


class PlannedDowntimeEndRequest(BaseModel):
    ended_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)

    @field_validator("ended_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)


def planned_downtime_api(event, now=None):
    """`duration_minutes` is the stored, final duration and stays null
    while the stop is open. `elapsed_minutes` is how long an OPEN stop
    has been running, measured against the server clock passed in - an
    event in progress must never read as zero just because it has not
    been closed yet."""
    if event is None:
        return None

    is_open = event["ended_at"] is None
    elapsed = (
        calc.minutes_between(event["started_at"], now)
        if is_open and now is not None
        else None
    )

    return {
        "planned_downtime_id": event["id"],
        "production_run_id": event["production_run_id"],
        "production_line": event["production_line"],
        "reason": event["reason"],
        "started_by": event["started_by"],
        "started_at": event["started_at"],
        "ended_by": event.get("ended_by"),
        "ended_at": event["ended_at"],
        "duration_minutes": _minutes(event["duration_minutes"]),
        "is_active": is_open,
        "elapsed_minutes": _minutes(elapsed),
    }


@router.post("/runs/{run_id}/planned-downtime", status_code=201)
def begin_planned_downtime(run_id: int, payload: PlannedDowntimeStartRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.started_by)

    idempotency = build_idempotency(
        idempotency_key,
        f"planned_downtime_start:{run_id}",
        payload,
        201,
        lambda event: {"status": "success", **planned_downtime_api(event)},
    )

    return run_idempotent_write(
        "start_planned_downtime",
        start_planned_downtime,
        run_id,
        payload.reason,
        payload.started_by,
        _now(),
        idempotency=idempotency,
    )


@router.post("/planned-downtime/{planned_downtime_id}/end")
def finish_planned_downtime(
    planned_downtime_id: int, payload: PlannedDowntimeEndRequest, idempotency_key: IdempotencyKey
):
    _require_known_technician(payload.ended_by)

    idempotency = build_idempotency(
        idempotency_key,
        f"planned_downtime_end:{planned_downtime_id}",
        payload,
        200,
        lambda event: {"status": "success", **planned_downtime_api(event)},
    )

    return run_idempotent_write(
        "end_planned_downtime",
        end_planned_downtime,
        planned_downtime_id,
        payload.ended_by,
        _now(),
        idempotency=idempotency,
    )


# ==========================================================
# REPORT TO ENGINEER
# ==========================================================


class FaultReportRequest(BaseModel):
    """machine_id / button_id are the Management-configured machine and
    fault button (GET /api/v1/hmi/config). When no configured fault
    button is chosen, a note describing the fault is required."""

    reported_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    machine: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    reason: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    machine_id: int | None = Field(default=None, ge=1)
    button_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("reported_by", "machine", "reason")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("note")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)

    @model_validator(mode="after")
    def button_and_note_rules(self):
        if self.button_id is not None and self.machine_id is None:
            raise ValueError("A fault button can only be sent together with its machine_id.")
        if self.button_id is None and self.note is None:
            raise ValueError(
                "Add a note describing the fault when no configured fault button is selected."
            )
        return self


def fault_report_api(created):
    return {
        "status": "success",
        "downtime_event_id": created["id"],
        "production_run_id": created["production_run_id"],
        "production_line": created["production_line"],
        "fault_id": created["fault_id"],
        "machine": created["machine"],
        "reason": created["reason"],
        "reported_by": created["reported_by"],
        "production_status": created["production_status"],
        "engineering_status": created["engineering_status"],
        "opened_at": created["opened_at"],
    }


@router.post("/runs/{run_id}/faults", status_code=201)
def report_fault(run_id: int, payload: FaultReportRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.reported_by)

    idempotency = build_idempotency(
        idempotency_key, f"fault_report:{run_id}", payload, 201, fault_report_api
    )

    return run_idempotent_write(
        "report_fault_to_engineering",
        report_fault_to_engineering,
        run_id,
        payload.model_dump(),
        _now(),
        idempotency=idempotency,
    )


# ==========================================================
# X-RAY COUNT (end of shift / run completion)
# ==========================================================


class XrayCountRequest(BaseModel):
    """Used for end-of-shift X-ray captures, the Complete Run preview and
    Complete Run itself.

    production_since_last_update is required: when true, the final
    pallets made since the last saved hourly update are recorded as a
    final hourly update in the SAME transaction, before the X-ray waste
    is calculated. Then exactly one of: a non-negative xray_pack_count,
    or count_unavailable=true with a reason."""

    line_technician: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    production_since_last_update: bool
    final_pallets_produced: Decimal | None = Field(
        default=None, gt=0, le=MAX_PALLETS_PER_UPDATE, decimal_places=4
    )
    count_unavailable: bool = False
    xray_pack_count: int | None = Field(default=None, ge=0, le=MAX_XRAY_PACK_COUNT)
    unavailable_reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("line_technician")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("unavailable_reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)

    @model_validator(mode="after")
    def consistent(self):
        if self.production_since_last_update and self.final_pallets_produced is None:
            raise ValueError("Enter the pallets produced since the last hourly update.")
        if not self.production_since_last_update and self.final_pallets_produced is not None:
            raise ValueError("Final pallets are only sent when production was made since the last update.")

        if self.count_unavailable:
            if self.unavailable_reason is None:
                raise ValueError("A reason is required when the X-ray count is unavailable.")
            if self.xray_pack_count is not None:
                raise ValueError("Do not send an X-ray count when it is marked unavailable.")
        else:
            if self.xray_pack_count is None:
                raise ValueError(
                    "The X-ray pack count is required unless 'Count unavailable' is selected."
                )
            if self.unavailable_reason is not None:
                raise ValueError(
                    "An unavailable reason is only allowed when the count is unavailable."
                )
        return self

    def as_capture(self):
        return {
            "line_technician": self.line_technician,
            "final_pallets_produced": self.final_pallets_produced,
            "count_available": not self.count_unavailable,
            "xray_pack_count": self.xray_pack_count,
            "unavailable_reason": self.unavailable_reason,
        }


def _waste_reason(status, warning):
    if status == "estimated":
        return None
    if status == "unavailable":
        return "X-ray count unavailable - no waste figure is calculated."
    if status == "data_quality_warning":
        return warning
    return "The X-ray count is zero, so no waste percentage applies."


def xray_capture_api(saved):
    """Shared with runs_api's Complete Run response."""
    status = saved["waste_status"]
    final = saved.get("final_hourly_update")

    return {
        "xray_capture_id": saved["xray_capture_id"],
        "capture_point": saved["capture_point"],
        "production_run_id": saved["production_run_id"],
        "production_line": saved["production_line"],
        "shift": saved["shift"],
        "captured_at": saved["captured_at"],
        "final_hourly_update_id": None if final is None else final["hourly_update_id"],
        "final_pallets_produced": None if final is None else _pallets(final["actual_pallets"]),
        "total_pallets_recorded": _pallets(saved["total_pallets_recorded"]),
        "count_available": saved["count_available"],
        "xray_pack_count": saved["xray_pack_count"],
        "unavailable_reason": saved["unavailable_reason"],
        "palletised_pallets": _pallets(saved["palletised_pallets"]),
        "palletised_packs": _packs(saved["palletised_packs"]),
        "post_xray_pack_difference": _packs(saved["post_xray_pack_difference"]),
        "estimated_post_xray_waste_percent": calc.as_number(
            saved["estimated_post_xray_waste_percent"], calc.PERCENT_PLACES
        ),
        "waste_status": status,
        "waste_unavailable_reason": _waste_reason(status, saved["warning"]),
        "data_quality_warning": saved["warning"],
        "calculation_status": "estimated" if status == "estimated" else "unavailable",
        "method": calc.XRAY_METHOD,
        "pallets_remaining": _pallets(saved.get("pallets_remaining")),
        "total_pallets_completed": _pallets(saved.get("total_pallets_completed")),
    }


@router.post("/runs/{run_id}/xray-counts", status_code=201)
def submit_shift_end_xray(run_id: int, payload: XrayCountRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)

    idempotency = build_idempotency(
        idempotency_key,
        f"xray_shift_end:{run_id}",
        payload,
        201,
        lambda saved: {"status": "success", **xray_capture_api(saved)},
    )

    return run_idempotent_write(
        "record_xray_capture",
        record_xray_capture,
        run_id,
        payload.as_capture(),
        _now(),
        False,
        idempotency=idempotency,
    )


@router.post("/runs/{run_id}/completion-preview")
def completion_preview(run_id: int, payload: XrayCountRequest):
    """Read-only. What Complete Run (or an end-of-shift X-ray capture)
    would record with these inputs - calculated by the backend so the
    review screen never recalculates anything. Nothing is saved."""
    basis = _call("get_completion_basis", get_completion_basis, run_id)

    if basis is None:
        raise HTTPException(status_code=404, detail=f"Production Run {run_id} was not found.")

    run = basis["run"]
    if run["status"] != "Active":
        raise HTTPException(status_code=409, detail=f"Production Run {run_id} is not active.")

    require_line_technician(run["production_line"], payload.line_technician)

    summary = calc.completion_summary(
        calc.PackConfig.from_row(run),
        basis["total_pallets"],
        basis["uncovered_pallets"],
        payload.final_pallets_produced,
        not payload.count_unavailable,
        payload.xray_pack_count,
    )
    status = summary["waste_status"]

    return {
        "production_run_id": run_id,
        "production_line": run["production_line"],
        "total_pallets_recorded": _pallets(summary["total_pallets_recorded"]),
        "final_pallets_produced": _pallets(summary["final_pallets_produced"]),
        "palletised_pallets": _pallets(summary["palletised_pallets"]),
        "palletised_packs": _packs(summary["palletised_packs"]),
        "count_available": not payload.count_unavailable,
        "xray_pack_count": payload.xray_pack_count,
        "post_xray_pack_difference": _packs(summary["post_xray_pack_difference"]),
        "estimated_post_xray_waste_percent": calc.as_number(
            summary["estimated_post_xray_waste_percent"], calc.PERCENT_PLACES
        ),
        "waste_status": status,
        "waste_unavailable_reason": _waste_reason(status, summary["warning"]),
        "data_quality_warning": summary["warning"],
        "calculation_status": "estimated" if status == "estimated" else "unavailable",
        "method": calc.XRAY_METHOD,
        # Completing on contradictory figures is refused by the write
        # path (409). The preview says so up front, so the HMI can block
        # Confirm and send the operator back to correct the input rather
        # than letting them commit and be rejected.
        "can_complete": status != "data_quality_warning",
        "blocking_reason": summary["warning"] if status == "data_quality_warning" else None,
        "saved": False,
    }


# ==========================================================
# CHANGEOVERS (one logical action with its planned stop)
# ==========================================================


class ChangeoverStartRequest(BaseModel):
    """The previous configuration is taken from the run itself; the
    technician enters the new one."""

    line_technician: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    new_customer: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    new_product: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    new_pack_weight_kg: Decimal = Field(gt=0, le=Decimal(2000), decimal_places=3)
    new_format: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    note: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("line_technician", "new_customer", "new_product", "new_format")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("note")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)


class ChangeoverCompleteRequest(BaseModel):
    """Sent when the first ACCEPTABLE packs of the new run are produced -
    not when the machines restart. The technician must confirm that
    explicitly."""

    completed_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    first_acceptable_packs_confirmed: Literal[True]
    note: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("completed_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("note")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)


def changeover_pair_api(result):
    return {
        "status": "success",
        "changeover": serialize_changeover(result["changeover"]),
        "planned_downtime": planned_downtime_api(result["planned_downtime"]),
    }


@router.post("/runs/{run_id}/changeovers", status_code=201)
def begin_changeover(run_id: int, payload: ChangeoverStartRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)

    idempotency = build_idempotency(
        idempotency_key, f"changeover_start:{run_id}", payload, 201, changeover_pair_api
    )

    return run_idempotent_write(
        "start_run_changeover",
        start_run_changeover,
        run_id,
        payload.line_technician,
        {
            "new_customer": payload.new_customer,
            "new_product": payload.new_product,
            "new_pack_weight_kg": payload.new_pack_weight_kg,
            "new_format": payload.new_format,
        },
        payload.note,
        _now(),
        idempotency=idempotency,
    )


@router.post("/changeovers/{changeover_id}/complete")
def finish_changeover(changeover_id: int, payload: ChangeoverCompleteRequest, idempotency_key: IdempotencyKey):
    _require_known_technician(payload.completed_by)

    idempotency = build_idempotency(
        idempotency_key, f"changeover_complete:{changeover_id}", payload, 200, changeover_pair_api
    )

    return run_idempotent_write(
        "complete_run_changeover",
        complete_run_changeover,
        changeover_id,
        payload.completed_by,
        payload.note,
        _now(),
        idempotency=idempotency,
    )


@router.get("/changeovers/open")
def open_changeover(production_line: str = Query(max_length=MAX_SHORT_TEXT_LENGTH)):
    _require_known_line(production_line)

    row = _call("get_open_changeover", get_open_changeover, production_line)

    return {"open_changeover": None if row is None else serialize_changeover(row)}


# ==========================================================
# ACTIVE-RUN RECOVERY
# ==========================================================


def _merged_minutes(intervals):
    return calc.total_minutes(intervals)


@router.get("/runs/{run_id}/hmi-state")
def hmi_run_state(run_id: int):
    """Authoritative state for restoring the tablet after a refresh:
    saved totals, open planned downtime and open changeover, all read
    from the database. Read-only - it never creates or changes a run."""
    state = _call("get_hmi_run_state", get_hmi_run_state, run_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Production Run {run_id} was not found.")

    now = _now()
    run = state["run"]
    hourly = state["hourly"]
    config = calc.PackConfig.from_row(run)

    pallets_recorded = calc.to_decimal(hourly["pallets_recorded"])
    expected = calc.to_decimal(hourly["expected_packs"])
    actual = config.pallets_to_packs(pallets_recorded)
    last_period_end = hourly["last_period_ended_at"]
    open_planned = next((e for e in state["planned"] if e["ended_at"] is None), None)

    # Three separate figures, all from the server clock (`now`, the same
    # instant reported as generated_at) - never from the tablet:
    #   completed = stops that have been closed,
    #   active    = the one open stop, measured to now,
    #   total     = every stop merged, so overlapping intervals are
    #               counted once and the total is the authority.
    planned_completed_minutes = _merged_minutes(
        (event["started_at"], event["ended_at"])
        for event in state["planned"]
        if event["ended_at"] is not None
    )
    planned_minutes = _merged_minutes(
        (event["started_at"], event["ended_at"] or now) for event in state["planned"]
    )
    unplanned_minutes = _merged_minutes(
        (fault["opened_at"], fault["resolved_at"] or now) for fault in state["faults"]
    )

    return {
        "generated_at": now,
        "run": {
            "run_id": run["id"],
            "production_line": run["production_line"],
            "line_technician": run["line_technician"],
            "shift": run["shift"],
            "customer": run["customer"],
            "product": run["product"],
            "format": run["format"],
            "pack_type": run["pack_type"],
            "pack_weight_kg": calc.as_number(run["pack_weight_kg"], calc.TONNES_PLACES),
            "packs_per_case": run["packs_per_case"],
            "cases_per_pallet": run["cases_per_pallet"],
            "target_speed_ppm": calc.as_number(run["target_speed_ppm"], calc.PACKS_PLACES),
            "status": run["status"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "starting_pallets_remaining": _pallets(run["starting_pallets_remaining"]),
            "pallets_remaining": _pallets(run["pallets_remaining"]),
            "total_pallets_completed": _pallets(run["total_pallets_completed"]),
            "potential_overrun_pallets": _pallets(run["potential_overrun_pallets"]),
        },
        "progress": {
            "hourly_update_count": hourly["hourly_update_count"],
            "pallets_recorded": _pallets(pallets_recorded),
            "expected_packs": _packs(expected),
            "actual_packs": _packs(actual),
            "output_gap_packs": _packs(max(expected - actual, calc.ZERO)),
            "expected_tonnes": calc.as_number(config.packs_to_tonnes(expected), calc.TONNES_PLACES),
            "actual_tonnes": calc.as_number(config.packs_to_tonnes(actual), calc.TONNES_PLACES),
            "production_achievement_percent": calc.as_number(
                calc.percent(actual, expected), calc.PERCENT_PLACES
            ),
            "planned_downtime_minutes": _minutes(planned_minutes),
            "planned_downtime_completed_minutes": _minutes(planned_completed_minutes),
            "planned_downtime_active_minutes": (
                None if open_planned is None
                else _minutes(calc.minutes_between(open_planned["started_at"], now))
            ),
            "changeover_active_minutes": (
                None if state["open_changeover"] is None
                else _minutes(calc.minutes_between(state["open_changeover"]["started_at"], now))
            ),
            "unplanned_downtime_minutes": _minutes(unplanned_minutes),
            "open_faults": sum(1 for f in state["faults"] if f["production_status"] == "Ongoing"),
            "last_period_ended_at": last_period_end,
            "next_hourly_update_due_at": calc.next_hourly_prompt_at(last_period_end or run["started_at"]),
        },
        "open_planned_downtime": planned_downtime_api(open_planned, now),
        "open_changeover": (
            None if state["open_changeover"] is None else serialize_changeover(state["open_changeover"])
        ),
    }
