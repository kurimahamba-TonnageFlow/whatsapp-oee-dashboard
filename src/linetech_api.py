"""LineTech configuration and verification on the existing changeover record."""
from datetime import datetime, timezone
from pathlib import Path
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from . import database as db, management_auth
from .hmi_auth import require_hmi_access
from .linetech import LineTechConfig, StrictModel, validate_config_references
from .pulse_capture_api import IdempotencyKey, build_idempotency, run_idempotent_write, require_line_technician

router = APIRouter(prefix="/api/v1", tags=["linetech"])


def configuration(line):
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            cursor.execute("SELECT id, linetech_config FROM public.production_lines WHERE name=%s AND active", (line,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(404, "Production line not found.")
            cursor.execute("SELECT id, name, active, display_order FROM public.machines WHERE production_line_id=%s ORDER BY display_order,id", (row["id"],))
            machines = cursor.fetchall()
            for machine in machines:
                cursor.execute("SELECT id,name,event_type,active,display_order FROM public.buttons WHERE machine_id=%s ORDER BY display_order,id", (machine["id"],))
                machine["buttons"] = cursor.fetchall()
    config = row["linetech_config"] or initial_config(machines)
    return {"config": config, "machines": machines}


def initial_config(machines):
    """Draft navigation from confirmed existing rows, never new fault names."""
    groups = [{"key": key, "label": label, "equipment": []} for key, label in
              [("sbs", "SBS / Bagger"), ("xray", "X-ray"), ("casepacker", "Case Packer"), ("robot", "Robot Palletiser")]]
    for m in machines:
        name = m["name"].casefold()
        index = 0 if name.startswith("sbs") else 1 if "x-ray" in name or "xray" in name else 2 if "casepacker" in name or "case packer" in name else 3 if "robot" in name else None
        if index is None:
            continue
        categories = {}
        for button in m["buttons"]:
            if button["event_type"] != "unplanned_fault":
                continue
            fault = button["name"].casefold()
            category = "Faults"
            if index == 0:
                category = ("Film" if "film" in fault else "Sealing" if "seal" in fault else
                            "Printer and label" if any(v in fault for v in ["label", "printer", "ribbon"]) else "Bag handling")
            categories.setdefault(category, []).append(button["id"])
        label = "BV1" if name.endswith("bv1") else "BV2" if name.endswith("bv2") else "Shared equipment" if index == 0 else m["name"]
        groups[index]["equipment"].append({"machine_id": m["id"], "label": label, "active": m["active"],
            "categories": [{"name": n, "button_ids": ids, "active": True} for n, ids in categories.items()]})
    catalogue = json.loads(Path(__file__).with_name("production_catalogue.json").read_text(encoding="utf-8"))
    return LineTechConfig(groups=groups, products=catalogue["products"], planned=[
        {"reason": "Film Change", "components": ["BV1", "BV2"]},
        {"reason": "Label Change", "components": ["Label 1", "Label 2"]},
        {"reason": "CCP Check", "components": []},
    ]).model_dump()


@router.get("/management/lines/{line}/linetech")
def get_configuration(line: str, actor=Depends(management_auth.require_management_session)):
    return configuration(line)


def save_config(line, config, actor, idempotency=None):
    validate_config_references(config, configuration(line)["machines"])
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            db._claim_idempotency(cursor, connection, idempotency)
            cursor.execute("SELECT * FROM public.production_lines WHERE name=%s AND active FOR UPDATE", (line,))
            before = cursor.fetchone()
            if before is None:
                raise db.PulseCaptureError(404, "Production line not found.")
            cursor.execute("UPDATE public.production_lines SET linetech_config=%s,updated_at=now() WHERE id=%s RETURNING *",
                           (db.Json(config.model_dump()), before["id"]))
            after = cursor.fetchone()
            db._configuration_audit(cursor, "linetech_configuration", actor, "production_line", before, after)
            result = {"status": "success", "config": config.model_dump()}
            db._store_idempotent_response(cursor, idempotency, result)
        connection.commit()
    return result


@router.post("/management/lines/{line}/linetech")
def set_configuration(line: str, payload: LineTechConfig, idempotency_key: IdempotencyKey,
                      actor=Depends(management_auth.require_management_session)):
    # Validate configuration references before entering the common write/error wrapper.
    try:
        validate_config_references(payload, configuration(line)["machines"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    key = build_idempotency(idempotency_key, f"linetech_config:{line}:{actor}", payload, 200, lambda x: x)
    return run_idempotent_write("linetech_configuration", save_config, line, payload, actor, idempotency=key)


@router.get("/lines/{line}/changeover-options", dependencies=[Depends(require_hmi_access)])
def options(line: str):
    config = configuration(line)["config"]
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            previous = db._latest_finished_run(cursor, line)
    return {"config": config, "previous": previous}


def changeover_context(stoppage_id):
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            cursor.execute("""SELECT c.*, s.physical_ended_at, s.ended_at AS restarted_at
                FROM public.changeovers c JOIN public.line_stoppages s ON s.id=c.line_stoppage_id
                WHERE s.id=%s""", (stoppage_id,))
            return cursor.fetchone()


@router.get("/line-stoppages/{stoppage_id}/linetech", dependencies=[Depends(require_hmi_access)])
def context(stoppage_id: int):
    return {"changeover": changeover_context(stoppage_id)}


class Verification(StrictModel):
    technician: str = Field(min_length=1, max_length=120)
    first_off: bool
    label: bool
    date_code: bool
    ccp: bool
    reference: str = Field(min_length=1, max_length=500)


class Cancellation(StrictModel):
    technician: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


def update_verification(stoppage_id, payload, cancel=False, idempotency=None):
    moment = datetime.now(timezone.utc)
    with db.get_database_connection() as connection:
        with connection.cursor(row_factory=db.dict_row) as cursor:
            db._claim_idempotency(cursor, connection, idempotency)
            cursor.execute("SELECT * FROM public.line_stoppages WHERE id=%s FOR UPDATE", (stoppage_id,))
            stop = cursor.fetchone()
            if stop is None or stop["ended_at"] is not None:
                raise db.PulseCaptureError(409, "An open changeover is required.")
            require_line_technician(stop["production_line"], payload.technician)
            cursor.execute("SELECT * FROM public.changeovers WHERE line_stoppage_id=%s FOR UPDATE", (stoppage_id,))
            record = cursor.fetchone()
            if not record or not record.get("workflow") or record["workflow"].get("cancelled_at"):
                raise db.PulseCaptureError(409, "No active LineTech changeover was found.")
            workflow = record["workflow"]
            if cancel:
                workflow.update(cancelled_at=moment.isoformat(), cancelled_by=payload.technician, cancellation_reason=payload.reason)
                cursor.execute("UPDATE public.casepacker_requests SET cancelled_at=%s WHERE line_stoppage_id=%s", (moment, stoppage_id))
                cursor.execute("UPDATE public.line_stoppages SET physical_ended_at=COALESCE(physical_ended_at,%s),physical_ended_by=COALESCE(physical_ended_by,%s) WHERE id=%s", (moment, payload.technician, stoppage_id))
            else:
                if workflow.get("qa_status") == "verified":
                    raise db.PulseCaptureError(409, "Verification is already recorded.")
                cursor.execute("SELECT id FROM public.casepacker_requests WHERE line_stoppage_id=%s AND ready_at IS NULL AND cancelled_at IS NULL", (stoppage_id,))
                if stop["physical_ended_at"] is None or cursor.fetchone():
                    raise db.PulseCaptureError(409, "Complete physical and Engineering work before verification.")
                if not all([payload.first_off, payload.label, payload.date_code, payload.ccp]):
                    raise db.PulseCaptureError(422, "All required checks must be confirmed from the actual QA record.")
                workflow.update(qa_status="verified", verification={**payload.model_dump(), "recorded_at": moment.isoformat()})
            cursor.execute("UPDATE public.changeovers SET workflow=%s WHERE id=%s", (db.Json(workflow), record["id"]))
            result = {"status": "success", "workflow": workflow}
            db._store_idempotent_response(cursor, idempotency, result)
        connection.commit()
    return result


@router.post("/line-stoppages/{stoppage_id}/verification", dependencies=[Depends(require_hmi_access)])
def verify(stoppage_id: int, payload: Verification, idempotency_key: IdempotencyKey):
    key = build_idempotency(idempotency_key, f"changeover_verify:{stoppage_id}", payload, 200, lambda x: x)
    return run_idempotent_write("changeover_verification", update_verification, stoppage_id, payload, idempotency=key)


@router.post("/line-stoppages/{stoppage_id}/cancel", dependencies=[Depends(require_hmi_access)])
def cancel(stoppage_id: int, payload: Cancellation, idempotency_key: IdempotencyKey):
    key = build_idempotency(idempotency_key, f"changeover_cancel:{stoppage_id}", payload, 200, lambda x: x)
    return run_idempotent_write("changeover_cancel", update_verification, stoppage_id, payload, True, idempotency=key)
