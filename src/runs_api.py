# ==========================================================
# TONNAGEFLOW PULSE
# Production Run API (HMI integration)
# ==========================================================
#
# HTTP-only. Start Run and Complete Run are HMI writes, so both require
# an `Idempotency-Key` header (see src/pulse_capture_api.py): the key,
# the business rows and the stored response share one database
# transaction, so a double tap or a retry after a timeout replays the
# original result instead of writing twice or reporting a misleading
# conflict.
#
# No CLI input functions (input(), choose_option(), collect_run_setup())
# are called from this module.

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

try:
    from .database import create_production_run, record_xray_capture
    from .main import line_technicians_by_line
    from .pulse_capture_api import (
        IdempotencyKey,
        XrayCountRequest,
        build_idempotency,
        load_run,
        require_line_technician,
        run_idempotent_write,
        strip_optional,
        xray_capture_api,
    )
except ImportError:
    from database import create_production_run, record_xray_capture
    from main import line_technicians_by_line
    from pulse_capture_api import (
        IdempotencyKey,
        XrayCountRequest,
        build_idempotency,
        load_run,
        require_line_technician,
        run_idempotent_write,
        strip_optional,
        xray_capture_api,
    )


router = APIRouter(prefix="/api/v1", tags=["runs"])


# ==========================================================
# REQUEST MODEL
# ==========================================================


class StartRunRequest(BaseModel):
    production_line: str
    line_technician: str
    shift: str
    customer: str
    product: str
    pack_weight: str
    pack_weight_kg: float = Field(gt=0)
    packs_per_case: int = Field(ge=1)
    pack_type: str
    target_speed_ppm: float = Field(gt=0)
    cases_per_pallet: int = Field(ge=1)
    pallets_remaining: int = Field(ge=0)
    previous_run_completed: int = Field(ge=0)
    # Optional so existing callers keep working; the QC changeover and
    # dashboard filters use it when sent.
    format: str | None = Field(default=None, max_length=120)

    @field_validator("format")
    @classmethod
    def optional_format(cls, value):
        return strip_optional(value)

    @field_validator(
        "production_line",
        "line_technician",
        "shift",
        "customer",
        "product",
        "pack_weight",
        "pack_type",
    )
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()

        if not stripped:
            raise ValueError("This field cannot be blank.")

        return stripped

    @field_validator("production_line")
    @classmethod
    def known_production_line(cls, value: str) -> str:
        if value not in line_technicians_by_line:
            raise ValueError(
                f"'{value}' is not a known Production Line."
            )

        return value

    @field_validator("line_technician")
    @classmethod
    def known_line_technician(cls, value: str, info) -> str:
        production_line = info.data.get("production_line")

        if production_line not in line_technicians_by_line:
            # production_line itself already failed validation above -
            # avoid raising a second, confusing error for the same cause.
            return value

        if value not in line_technicians_by_line[production_line]:
            raise ValueError(
                f"'{value}' is not a known Line Technician "
                f"for Production Line '{production_line}'."
            )

        return value


# ==========================================================
# START RUN
# ==========================================================


def _start_run_response(result):
    return {
        "status": "success",
        "message": "Run started",
        "run_id": result["run_id"],
        "production_line": result["production_line"],
        "line_technician": result["line_technician"],
        "pallets_remaining": result["pallets_remaining"],
    }


@router.post("/runs", status_code=201)
def start_run(payload: StartRunRequest, idempotency_key: IdempotencyKey):
    database_run = {
        "production_line": payload.production_line,
        "line_technician": payload.line_technician,
        "shift": payload.shift,
        "customer": payload.customer,
        "product": payload.product,
        "pack_weight_kg": payload.pack_weight_kg,
        "packs_per_case": payload.packs_per_case,
        "pack_type": payload.pack_type,
        "target_speed_ppm": payload.target_speed_ppm,
        "cases_per_pallet": payload.cases_per_pallet,
        "starting_pallets_remaining": payload.pallets_remaining,
        "pallets_remaining": payload.pallets_remaining,
        "previous_run_completed": payload.previous_run_completed,
        "format": payload.format,
    }

    idempotency = build_idempotency(
        idempotency_key,
        f"run_start:{payload.production_line}",
        payload,
        201,
        _start_run_response,
    )

    return run_idempotent_write(
        "create_production_run", create_production_run, database_run, idempotency=idempotency
    )


# ==========================================================
# COMPLETE RUN
# ==========================================================


@router.post("/runs/{run_id}/complete", status_code=200)
def complete_run(run_id: int, payload: XrayCountRequest, idempotency_key: IdempotencyKey):
    """Completing a run REQUIRES:
      - whether production was made since the last hourly update, and if
        so the final pallets (saved as a final hourly update FIRST, so
        the X-ray waste estimate includes them);
      - the end-of-run X-ray pack count, or count_unavailable=true with
        a reason.
    The final hourly update, the X-ray record and the run's Completed
    status are written in ONE transaction - all of them or none."""
    run = load_run(run_id)
    require_line_technician(run["production_line"], payload.line_technician)

    def response(saved):
        return {
            "status": "success",
            "message": "Run completed",
            "run_id": run_id,
            "production_line": saved["production_line"],
            "run_status": "Completed",
            "xray": xray_capture_api(saved),
        }

    idempotency = build_idempotency(
        idempotency_key, f"run_complete:{run_id}", payload, 200, response
    )

    return run_idempotent_write(
        "record_xray_capture",
        record_xray_capture,
        run_id,
        payload.as_capture(),
        datetime.now(timezone.utc),
        True,
        idempotency=idempotency,
    )
