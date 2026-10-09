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
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from .api_idempotency import IdempotencyKey, build_idempotency, run_idempotent_write
    from .api_logging import log_operation_failure
    from . import management_auth
    from . import pulse_calculations as calc
    from .database import (
        PulseCaptureError,
        acknowledge_line_fault,
        complete_run_changeover,
        end_line_stoppage,
        end_planned_downtime,
        get_completion_basis,
        get_hmi_run_state,
        get_casepacker_requests,
        get_open_changeover,
        get_open_line_faults,
        get_production_run_by_id,
        get_run_hour_readings,
        record_hourly_update,
        review_hourly_loss,
        record_target_speed_change,
        record_operating_speed_change,
        reclassify_line_stoppage,
        record_xray_capture,
        report_fault_to_engineering,
        restore_fault_production,
        start_line_stoppage,
        start_planned_downtime,
        start_run_changeover,
    )
    from .dashboard_reports import LINE_STOP_DOWNTIME_TYPE, serialize_changeover
    from .factory_time import CLOCK_HOUR, clock_hour_label, clock_hours_between, is_clock_hour_start, clock_hour_start
    from .main import line_technicians_by_line
except ImportError:
    from api_idempotency import IdempotencyKey, build_idempotency, run_idempotent_write
    from api_logging import log_operation_failure
    import management_auth
    import pulse_calculations as calc
    from database import (
        PulseCaptureError,
        acknowledge_line_fault,
        complete_run_changeover,
        end_line_stoppage,
        end_planned_downtime,
        get_completion_basis,
        get_hmi_run_state,
        get_casepacker_requests,
        get_open_changeover,
        get_open_line_faults,
        get_production_run_by_id,
        get_run_hour_readings,
        record_hourly_update,
        review_hourly_loss,
        record_target_speed_change,
        record_operating_speed_change,
        reclassify_line_stoppage,
        record_xray_capture,
        report_fault_to_engineering,
        restore_fault_production,
        start_line_stoppage,
        start_planned_downtime,
        start_run_changeover,
    )
    from dashboard_reports import LINE_STOP_DOWNTIME_TYPE, serialize_changeover
    from factory_time import CLOCK_HOUR, clock_hour_label, clock_hours_between, is_clock_hour_start, clock_hour_start
    from main import line_technicians_by_line


router = APIRouter(prefix="/api/v1", tags=["hmi-capture"])

MAX_PALLETS_PER_UPDATE = Decimal(1000)
MAX_XRAY_PACK_COUNT = 10_000_000
MAX_TEXT_LENGTH = 500
MAX_SHORT_TEXT_LENGTH = 120
CHANGEOVER_REASON = "Changeover"

def _now():
    return datetime.now(timezone.utc)


def safe_503():
    return HTTPException(status_code=503, detail="Could not save this to Pulse. Please try again.")


def _call(operation_name, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)

    except PulseCaptureError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    except Exception as error:
        log_operation_failure("hmi_capture", operation_name, error)
        raise safe_503()


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
    # The named factory clock hour this reading is for, as its start
    # instant (e.g. "2026-01-12T06:00:00Z" for 06:00-07:00 GMT).
    hour_start: datetime
    # Send as a string ("3.75") to keep exact decimal precision end to end.
    pallets_produced: Decimal = Field(ge=0, le=MAX_PALLETS_PER_UPDATE, decimal_places=4)
    other_loss_reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("line_technician")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("hour_start")
    @classmethod
    def whole_clock_hour(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("hour_start must include a time zone.")
        if not is_clock_hour_start(value):
            raise ValueError("hour_start must be the start of a clock hour.")
        return value.astimezone(timezone.utc)

    @field_validator("other_loss_reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)


def hourly_update_api(saved):
    config = saved["config"]
    expected = calc.to_decimal(saved["expected_packs"])
    actual = calc.to_decimal(saved["actual_packs"])

    review = saved.get("loss_review") or {}
    report = review.get("production_report")
    oee = review.get("estimated_oee") or {
        "availability_percent": None, "performance_percent": None,
        "estimated_quality_percent": None, "estimated_oee_percent": None,
        "unavailable_reason": "Awaiting downtime data", "quality_basis": "provisional",
        "output_basis": "Palletised packs - provisional output basis", "warnings": [],
    }

    return {
        "status": "success",
        "hourly_update_id": saved["hourly_update_id"],
        "loss_review": saved.get("loss_review"),
        "estimated_oee": oee,
        "production_report": report,
        "standard_speed_ppm": report.get("standard_speed_ppm") if report else None,
        "unplanned_downtime_minutes": _minutes(review.get("unplanned_minutes")),
        "production_run_id": saved["production_run_id"],
        "production_line": saved["production_line"],
        "hour_start": saved["hour_start"],
        "hour_label": saved["hour_label"],
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


@router.post("/runs/{run_id}/hourly-loss-review")
def hourly_loss_review(run_id: int, payload: HourlyUpdateRequest):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)
    return _call("review_hourly_loss", review_hourly_loss, run_id, payload.hour_start, payload.pallets_produced, _now())


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
        payload.hour_start,
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
    component: str | None = Field(default=None, min_length=1, max_length=40)
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
        "component": event.get("component"),
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
        **({"component": payload.component} if payload.component is not None else {}),
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


class ProductionRestoreRequest(BaseModel):
    production_line: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    technician: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    note: str = Field(max_length=MAX_TEXT_LENGTH)
    restored_at: datetime

    @field_validator("production_line", "technician", "note")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("restored_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Restart time must include a time zone.")
        return value


@router.post("/faults/{fault_id}/production-restored")
def restore_production(fault_id: int, payload: ProductionRestoreRequest, idempotency_key: IdempotencyKey):
    require_line_technician(payload.production_line, payload.technician)
    idempotency = build_idempotency(idempotency_key, f"production_restore:{fault_id}", payload, 200, lambda row: row)
    return run_idempotent_write(
        "restore_fault_production", restore_fault_production, fault_id,
        payload.production_line, payload.technician, payload.note, payload.restored_at,
        _now(), idempotency=idempotency,
    )


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
    outcome: Literal["call_engineer", "resolved", "resolved_waiting_restart"] = "call_engineer"
    started_at: datetime | None = None
    restored_at: datetime | None = None

    @field_validator("started_at", "restored_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Downtime times must include a time zone.")
        return value

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
        if self.outcome == "resolved":
            if self.started_at is None or self.restored_at is None:
                raise ValueError("Resolved downtime needs start time and confirmed restart time.")
            if self.restored_at < self.started_at:
                raise ValueError("Restart cannot be before the stop started.")
        elif self.outcome == "resolved_waiting_restart":
            if self.started_at is None or self.restored_at is not None:
                raise ValueError("A repaired fault awaiting restart needs a start time and no restart time.")
        elif self.started_at is not None or self.restored_at is not None:
            raise ValueError("Use the resolved option to report an already completed stop.")
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
        "linetech_resolved_at": created.get("linetech_resolved_at"),
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
    other_loss_reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
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
            "other_loss_reason": self.other_loss_reason,
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
        "loss_review": None if final is None else final.get("loss_review"),
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
        "loss_review": _call("review_hourly_loss", review_hourly_loss, run_id, clock_hour_start(_now()),
                             payload.final_pallets_produced or Decimal(0), _now(), final=True),
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
            "standard_speed_ppm": calc.as_number(run.get("standard_speed_ppm"), calc.PACKS_PLACES),
            "standard_version_id": run.get("standard_version_id"),
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
        "target_speed_changes": [speed_change_api(change) for change in state.get("speed_changes", [])],
        "operating_speed_changes": [speed_change_api(change) for change in state.get("operating_changes", [])],
        "hours": run_hours_api(run, {h: None for h in state.get("reported_hours", [])}, now),
        "line_faults": [line_fault_api(fault) for fault in state.get("line_faults", [])],
    }


# ==========================================================
# FIXED CLOCK HOURS (what the HMI asks the technician for)
# ==========================================================


def run_hours_api(run, readings, now):
    """Every clock hour the run has been open in, oldest first:
    `reported`, `due` (finished and not yet reported - each missed hour
    is asked for on its own) or `in_progress` (the current hour; it is
    reported after it ends, or as the final part hour at End Run).
    `readings` maps hour_start -> pallets (or None when only the fact of
    a reading is known)."""
    end = run["finished_at"] or now
    items = []
    for hour_start in clock_hours_between(run["started_at"], end):
        window = calc.reading_window(hour_start, run["started_at"], run["finished_at"])
        if window is None:
            continue
        start, final_end = window
        finished = run["finished_at"] is not None or hour_start + CLOCK_HOUR <= now
        if hour_start in readings:
            status = "reported"
        elif finished:
            status = "due"
        else:
            status = "in_progress"
        minutes = calc.minutes_between(start, min(final_end, now))
        items.append(
            {
                "hour_start": hour_start,
                "hour_end": hour_start + CLOCK_HOUR,
                "hour_label": clock_hour_label(hour_start),
                "status": status,
                "pallets_produced": _pallets(readings.get(hour_start)),
                "applicable_minutes": _minutes(minutes),
                "is_partial_hour": calc.minutes_between(start, final_end) < calc.SIXTY,
            }
        )

    due = [item for item in items if item["status"] == "due"]
    current = next((item for item in items if item["status"] == "in_progress"), None)
    return {
        "hours": items,
        "due_count": len(due),
        "next_due_hour": due[0] if due else None,
        "current_hour": current,
    }


@router.get("/runs/{run_id}/hours")
def run_hours(run_id: int):
    """Read-only. The HMI asks for each `due` hour separately."""
    data = _call("get_run_hour_readings", get_run_hour_readings, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Production Run {run_id} was not found.")
    readings = {row["hour_start"]: row["pallets_completed"] for row in data["readings"]}
    return {"production_run_id": run_id, **run_hours_api(data["run"], readings, _now())}


# ==========================================================
# TARGET SPEED CHANGE (mid-run, forward only)
# ==========================================================


class TargetSpeedChangeRequest(BaseModel):
    line_technician: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    new_target_speed_ppm: Decimal = Field(gt=0, le=Decimal(10_000), decimal_places=4)
    reason: str = Field(max_length=MAX_TEXT_LENGTH)

    @field_validator("line_technician", "reason")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)


def speed_change_api(change):
    return {
        "change_id": change.get("id"),
        "previous_speed_ppm": calc.as_number(change["previous_speed_ppm"], calc.PACKS_PLACES),
        "new_speed_ppm": calc.as_number(change["new_speed_ppm"], calc.PACKS_PLACES),
        "reason": change.get("reason"),
        "changed_by": change.get("changed_by"),
        "effective_at": change["effective_at"],
        "submitted_at": change.get("submitted_at"),
        "supersedes_id": change.get("supersedes_id"),
    }


@router.post("/runs/{run_id}/target-speed", status_code=201)
def change_target_speed(run_id: int, payload: TargetSpeedChangeRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)

    idempotency = build_idempotency(
        idempotency_key,
        f"target_speed:{run_id}",
        payload,
        201,
        lambda saved: {"status": "success", "production_run_id": run_id, **speed_change_api(saved)},
    )
    return run_idempotent_write(
        "record_target_speed_change",
        record_target_speed_change,
        run_id,
        payload.new_target_speed_ppm,
        payload.reason,
        payload.line_technician,
        _now(),
        idempotency=idempotency,
    )


class OperatingSpeedChangeRequest(BaseModel):
    line_technician: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    new_operating_speed_ppm: Decimal = Field(ge=0, le=Decimal(10_000), decimal_places=4)
    reason: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    effective_at: datetime | None = None
    supersedes_id: int | None = Field(default=None, gt=0)

    @field_validator("line_technician", "reason")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Effective time must include its timezone.")
        return value


@router.post("/runs/{run_id}/operating-speed", status_code=201)
def change_operating_speed(run_id: int, payload: OperatingSpeedChangeRequest, idempotency_key: IdempotencyKey):
    run = load_run(run_id)
    # HMI currently has no authenticated person: retain the validated reporting technician.
    require_line_technician(run["production_line"], payload.line_technician)
    idempotency = build_idempotency(idempotency_key, f"operating_speed:{run_id}", payload, 201,
        lambda saved: {"status": "success", "production_run_id": run_id, **speed_change_api(saved)})
    return run_idempotent_write("record_operating_speed_change", record_operating_speed_change,
        run_id, payload.new_operating_speed_ppm, payload.reason, payload.line_technician,
        payload.effective_at, _now(), payload.supersedes_id, idempotency=idempotency)


# ==========================================================
# END RUN -> CHANGEOVER / OTHER (line stoppages between runs)
# ==========================================================


class LineStoppageStartRequest(BaseModel):
    changeover_selection: dict | None = None
    casepacker_required: bool = False
    casepacker_details: str | None = Field(default=None, max_length=500)
    kind: Literal["changeover", "other", "handover", "not_scheduled"]
    started_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("started_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)

    @model_validator(mode="after")
    def other_needs_a_reason(self):
        if self.changeover_selection is not None:
            from .linetech import ChangeoverSelection
            if self.kind != "changeover":
                raise ValueError("Changeover selection requires a changeover stop.")
            self.changeover_selection = ChangeoverSelection.model_validate(self.changeover_selection).model_dump()
        if self.kind == "other" and not self.reason:
            raise ValueError("Write the reason the line is stopped.")
        if self.casepacker_required:
            if self.kind != "changeover":
                raise ValueError("Casepacker work must be linked to a changeover.")
            if not self.casepacker_details or not self.casepacker_details.strip():
                raise ValueError("Describe the required casepacker format or program change.")
            self.casepacker_details = self.casepacker_details.strip()
        elif self.casepacker_details:
            raise ValueError("Select casepacker change required before adding details.")
        return self


class ManagerNextStepRequest(BaseModel):
    kind: Literal["changeover", "other", "handover", "not_scheduled"]
    reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)

    @model_validator(mode="after")
    def other_needs_a_reason(self):
        if self.kind == "other" and not self.reason:
            raise ValueError("Write the reason the line is stopped.")
        return self


class LineStoppageEndRequest(BaseModel):
    ended_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)

    @field_validator("ended_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)


def _span(start, end):
    return None if start is None or end is None else _minutes(calc.minutes_between(start, end))


def line_stoppage_api(result, now=None):
    """Changeover times: physical (Changeover -> End Changeover), new-run
    setup (End Changeover -> new run starts) and total (both, counted
    once against the line). A Handover records both technicians:
    started_by = outgoing, ended_by = incoming. Resolving an Other stop
    also returns the Restart delay it started."""
    body = _line_stoppage_body(result["stoppage"])
    body["changeover"] = None if result.get("changeover") is None else serialize_changeover(result["changeover"])
    delay = result.get("restart_delay")
    body["restart_delay"] = None if delay is None else _line_stoppage_body(delay)
    audit = result.get("reclassification")
    if audit is not None:
        body["reclassification"] = {
            "reclassification_id": audit["id"],
            "previous_kind": audit["previous_kind"],
            "previous_reason": audit["previous_reason"],
            "new_kind": audit["new_kind"],
            "new_reason": audit["new_reason"],
            "changed_by": audit["changed_by"],
            "changed_at": audit["changed_at"],
            "note": audit["note"],
        }
    return body


def _line_stoppage_body(stoppage):
    is_open = stoppage["ended_at"] is None
    physical_end = stoppage.get("physical_ended_at")
    return {
        "status": "success",
        "stoppage_id": stoppage["id"],
        "production_line": stoppage["production_line"],
        "kind": stoppage["kind"],
        # Changeover and Handover are planned; Other and Restart delay are
        # unplanned; Not scheduled is neither.
        "downtime_type": LINE_STOP_DOWNTIME_TYPE.get(stoppage["kind"], "unplanned"),
        "reason": stoppage["reason"],
        "previous_production_run_id": stoppage["previous_production_run_id"],
        "next_production_run_id": stoppage["next_production_run_id"],
        "follows_stoppage_id": stoppage.get("follows_stoppage_id"),
        "started_by": stoppage["started_by"],
        "started_at": stoppage["started_at"],
        "ended_by": stoppage["ended_by"],
        "ended_at": stoppage["ended_at"],
        "duration_minutes": _minutes(stoppage["duration_minutes"]),
        "physical_ended_at": physical_end,
        "physical_ended_by": stoppage.get("physical_ended_by"),
        "physical_minutes": _span(stoppage["started_at"], physical_end),
        "setup_minutes": _span(physical_end, stoppage["ended_at"]),
        "total_minutes": _span(stoppage["started_at"], stoppage["ended_at"]),
        "is_active": is_open,
    }


@router.post("/lines/{production_line}/stoppages", status_code=201)
def begin_line_stoppage(production_line: str, payload: LineStoppageStartRequest, idempotency_key: IdempotencyKey):
    _require_known_line(production_line)
    require_line_technician(production_line, payload.started_by)

    idempotency = build_idempotency(
        idempotency_key, f"line_stoppage:{production_line}", payload, 201, line_stoppage_api
    )
    return run_idempotent_write(
        "start_line_stoppage",
        start_line_stoppage,
        production_line,
        payload.kind,
        payload.reason,
        payload.started_by,
        _now(),
        *([payload.casepacker_details] if payload.casepacker_required else []),
        idempotency=idempotency,
        **({"changeover_selection": payload.changeover_selection} if payload.changeover_selection is not None else {}),
    )


@router.post("/lines/{production_line}/next-step/manager", status_code=201)
def manager_next_step(
    production_line: str,
    payload: ManagerNextStepRequest,
    idempotency_key: IdempotencyKey,
    manager_name: str = Depends(management_auth.require_management_session),
):
    """An authorised manager records what happened after a run whose End
    Run choice was never made - e.g. days later. Same rules as the HMI
    choice: one choice per ended run, and the event starts when that run
    ended. The manager is recorded as '<name> (manager)'."""
    _require_known_line(production_line)
    idempotency = build_idempotency(
        idempotency_key, f"line_next_step_manager:{production_line}", payload, 201, line_stoppage_api
    )
    return run_idempotent_write(
        "start_line_stoppage",
        start_line_stoppage,
        production_line,
        payload.kind,
        payload.reason,
        f"{manager_name} (manager)",
        _now(),
        idempotency=idempotency,
    )


class LineStoppageReclassifyRequest(BaseModel):
    new_kind: Literal["handover", "other", "not_scheduled", "restart_delay"]
    reason: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    note: str = Field(max_length=MAX_TEXT_LENGTH)

    @field_validator("reason")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)

    @field_validator("note")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @model_validator(mode="after")
    def other_needs_a_reason(self):
        if self.new_kind == "other" and not self.reason:
            raise ValueError("Write the reason the line was stopped.")
        return self


@router.post("/line-stoppages/{stoppage_id}/reclassify")
def reclassify_stoppage(
    stoppage_id: int,
    payload: LineStoppageReclassifyRequest,
    idempotency_key: IdempotencyKey,
    manager_name: str = Depends(management_auth.require_management_session),
):
    """An authorised manager corrects a line stop's classification (e.g.
    Other -> Not scheduled). The stop stays one interval; the previous
    and new classification, who, when and why are kept in the audit
    trail, and every report recalculates from the corrected row."""
    idempotency = build_idempotency(
        idempotency_key, f"line_stoppage_reclassify:{stoppage_id}", payload, 200, line_stoppage_api
    )
    return run_idempotent_write(
        "reclassify_line_stoppage",
        reclassify_line_stoppage,
        stoppage_id,
        payload.new_kind,
        payload.reason,
        manager_name,
        payload.note,
        _now(),
        idempotency=idempotency,
    )


@router.post("/line-stoppages/{stoppage_id}/end")
def finish_line_stoppage(stoppage_id: int, payload: LineStoppageEndRequest, idempotency_key: IdempotencyKey):
    _require_known_technician(payload.ended_by)

    idempotency = build_idempotency(
        idempotency_key, f"line_stoppage_end:{stoppage_id}", payload, 200, line_stoppage_api
    )
    return run_idempotent_write(
        "end_line_stoppage",
        end_line_stoppage,
        stoppage_id,
        payload.ended_by,
        _now(),
        idempotency=idempotency,
    )


# ==========================================================
# CARRIED FAULTS: acknowledge and escalate
# ==========================================================


def line_fault_api(fault):
    return {
        "downtime_event_id": fault["downtime_event_id"],
        "production_run_id": fault["production_run_id"],
        "fault_id": fault["fault_id"],
        "machine": fault["machine"],
        "reason": fault["reason"],
        "reported_by": fault["reported_by"],
        "engineer": fault["engineer"],
        "engineering_status": fault["engineering_status"],
        "opened_at": fault["opened_at"],
        "escalation_count": fault["escalation_count"],
        "last_escalated_at": fault["last_escalated_at"],
        "last_escalated_by": fault["last_escalated_by"],
        "acknowledged": fault["acknowledged"],
    }


@router.get("/lines/{production_line}/open-faults")
def open_line_faults(production_line: str):
    """Faults still open on the line from any run. `acknowledged` means
    acknowledged since the last run on the line ended."""
    _require_known_line(production_line)
    data = _call("get_open_line_faults", get_open_line_faults, production_line)
    faults = [line_fault_api(fault) for fault in data["faults"]]
    return {
        "production_line": production_line,
        "handover_at": data["handover_at"],
        "faults": faults,
        "unacknowledged_count": sum(1 for fault in faults if not fault["acknowledged"]),
    }


class FaultAcknowledgeRequest(BaseModel):
    production_line: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    acknowledged_by: str = Field(max_length=MAX_SHORT_TEXT_LENGTH)
    note: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)

    @field_validator("production_line", "acknowledged_by")
    @classmethod
    def required_text(cls, value):
        return strip_required(value)

    @field_validator("note")
    @classmethod
    def optional_text(cls, value):
        return strip_optional(value)


@router.post("/faults/{downtime_event_id}/acknowledge")
def acknowledge_fault(downtime_event_id: int, payload: FaultAcknowledgeRequest, idempotency_key: IdempotencyKey):
    """Acknowledge AND escalate: updates the existing fault's escalation
    fields. It never creates a new fault."""
    _require_known_line(payload.production_line)
    require_line_technician(payload.production_line, payload.acknowledged_by)

    idempotency = build_idempotency(
        idempotency_key,
        f"fault_acknowledge:{downtime_event_id}",
        payload,
        200,
        lambda saved: {"status": "success", "escalated": True, **saved},
    )
    return run_idempotent_write(
        "acknowledge_line_fault",
        acknowledge_line_fault,
        downtime_event_id,
        payload.production_line,
        payload.acknowledged_by,
        payload.note,
        _now(),
        idempotency=idempotency,
    )


@router.get("/line-stoppages/{stoppage_id}/casepacker")
def casepacker_status(stoppage_id: int):
    items = _call("get_casepacker_requests", get_casepacker_requests, stoppage_id)
    return {"request": items[0] if items else None}
