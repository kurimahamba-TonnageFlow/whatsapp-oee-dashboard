"""Management owns versioned standards. Run-start snapshots are selected by the database."""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
try:
    from . import database as db, management_auth
    from .main import line_technicians_by_line
    from .pulse_capture_api import IdempotencyKey, build_idempotency, run_idempotent_write
except ImportError:
    import database as db, management_auth
    from main import line_technicians_by_line
    from pulse_capture_api import IdempotencyKey, build_idempotency, run_idempotent_write

router = APIRouter(prefix="/api/v1", tags=["production standards"])

class StandardConfiguration(BaseModel):
    production_line: str
    product: str = Field(min_length=1, max_length=120)
    pack_type: str = Field(min_length=1, max_length=120)
    pack_weight_kg: Decimal = Field(gt=0, decimal_places=4)
    packs_per_case: int = Field(gt=0)
    cases_per_pallet: int = Field(gt=0)

    @field_validator("product", "pack_type", "production_line")
    @classmethod
    def required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A value is required.")
        return value

    @field_validator("production_line")
    @classmethod
    def known_line(cls, value):
        if value not in line_technicians_by_line:
            raise ValueError("Unknown production line.")
        return value

class StandardVersionRequest(StandardConfiguration):
    standard_speed_ppm: Decimal = Field(gt=0, le=10000, decimal_places=4)
    effective_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Effective time must include a timezone.")
        return value

    @field_validator("reason")
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError("A reason is required.")
        return value.strip()

_MATCH = """production_line = %(production_line)s
 AND public.canonical_product(product) = public.canonical_product(%(product)s)
 AND lower(trim(pack_type)) = lower(trim(%(pack_type)s))
 AND pack_weight_kg = %(pack_weight_kg)s AND packs_per_case = %(packs_per_case)s
 AND cases_per_pallet = %(cases_per_pallet)s"""


def record_standard(values, manager_name, idempotency=None):
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            db._claim_idempotency(cursor, connection, idempotency)
            cursor.execute("""INSERT INTO public.production_standard_versions
 (production_line,product,pack_type,pack_weight_kg,packs_per_case,cases_per_pallet,
 standard_speed_ppm,effective_at,reason,manager_name)
 VALUES (%(production_line)s,%(product)s,%(pack_type)s,%(pack_weight_kg)s,
 %(packs_per_case)s,%(cases_per_pallet)s,%(standard_speed_ppm)s,%(effective_at)s,
 %(reason)s,%(manager_name)s) RETURNING *""", {**values, "manager_name": manager_name})
            result = cursor.fetchone()
            db._store_idempotent_response(cursor, idempotency, result)
        connection.commit()
    return result


@router.post("/management/production-standards", status_code=201)
def create_standard(payload: StandardVersionRequest, idempotency_key: IdempotencyKey,
                    manager_name: str = Depends(management_auth.require_management_session)):
    idempotency = build_idempotency(idempotency_key, "management_standard:" + manager_name,
                                   payload, 201, lambda result: result)
    return run_idempotent_write("record_standard", record_standard, payload.model_dump(),
                               manager_name, idempotency=idempotency)


@router.get("/management/production-standards")
def standard_history(manager_name: str = Depends(management_auth.require_management_session)):
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            cursor.execute("SELECT * FROM public.production_standard_versions ORDER BY effective_at DESC, id DESC")
            return cursor.fetchall()


@router.post("/production-standards/resolve")
def resolve_standard(payload: StandardConfiguration):
    # Read-only preview for the HMI. Start Run resolves again at its own timestamp.
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            cursor.execute("SELECT id,standard_speed_ppm,effective_at FROM public.production_standard_versions WHERE "
                           + _MATCH + " AND effective_at <= %(at)s ORDER BY effective_at DESC,id DESC LIMIT 1",
                           {**payload.model_dump(), "at": datetime.now(timezone.utc)})
            result = cursor.fetchone()
    if result is None:
        raise HTTPException(409, "Management must configure a standard for this line, product and pack configuration.")
    return result
