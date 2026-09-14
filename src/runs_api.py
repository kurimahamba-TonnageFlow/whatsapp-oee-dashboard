# ==========================================================
# TONNAGEFLOW PULSE
# Production Run API (HMI integration)
# ==========================================================
#
# HTTP-only. Reuses the existing engine's data and persistence:
#   - src.main.line_technicians_by_line for known-line/technician checks
#   - src.database.get_active_production_run to block duplicate active runs
#   - src.database.save_production_run to persist the run
#
# No CLI input functions (input(), choose_option(), collect_run_setup())
# are called from this module.

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    from .database import get_active_production_run, save_production_run
    from .main import line_technicians_by_line
except ImportError:
    from database import get_active_production_run, save_production_run
    from main import line_technicians_by_line


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
# DUPLICATE-SUBMISSION GUARD
# ==========================================================
# A non-blocking per-line lock. If a second Start Run request for the
# same Production Line arrives while the first is still being checked
# / persisted, it is rejected immediately instead of racing the first
# request to read/write the active-run state.

_line_locks: dict[str, threading.Lock] = {}
_line_locks_guard = threading.Lock()


def _lock_for_line(production_line: str) -> threading.Lock:
    with _line_locks_guard:
        return _line_locks.setdefault(production_line, threading.Lock())


# ==========================================================
# START RUN
# ==========================================================


@router.post("/runs", status_code=201)
def start_run(payload: StartRunRequest):
    lock = _lock_for_line(payload.production_line)

    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=(
                "A Run Start request for Production Line "
                f"'{payload.production_line}' is already being processed."
            ),
        )

    try:
        try:
            active_run = get_active_production_run(payload.production_line)

        except Exception:
            print("DATABASE ERROR")
            print("Could not check for an active run.")

            raise HTTPException(
                status_code=503,
                detail=(
                    "Could not verify existing Production Runs. "
                    "Please try again."
                ),
            )

        if active_run is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Production Line '{payload.production_line}' "
                    "already has an active Production Run."
                ),
            )

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
        }

        try:
            run_id = save_production_run(database_run)

        except Exception:
            print("DATABASE ERROR")
            print("Production Run was NOT saved to Supabase.")

            raise HTTPException(
                status_code=503,
                detail=(
                    "Production Run could not be saved. Please try again."
                ),
            )

        return {
            "status": "success",
            "message": "Run started",
            "run_id": run_id,
            "production_line": payload.production_line,
            "line_technician": payload.line_technician,
            "pallets_remaining": payload.pallets_remaining,
        }

    finally:
        lock.release()
