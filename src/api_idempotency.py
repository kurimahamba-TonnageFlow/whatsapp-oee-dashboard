"""Shared HTTP idempotency helpers, independent of the interactive CLI."""
import hashlib
import json
from typing import Annotated
from fastapi import Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
try:
    from .api_logging import log_operation_failure
    from .database import IdempotencyRequest, IdempotentReplay, PulseCaptureError
except ImportError:
    from api_logging import log_operation_failure
    from database import IdempotencyRequest, IdempotentReplay, PulseCaptureError


def safe_503():
    return HTTPException(status_code=503, detail="Could not save this to Pulse. Please try again.")


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


def build_idempotency(key, action, payload, status_code, to_body):
    """payload: the validated request model. The fingerprint covers the
    action (which includes the path id) and the full request body."""
    values = payload.model_dump(mode="json")
    # Additive LineTech fields must not invalidate a pre-upgrade tablet's retry.
    for field in ("component", "changeover_selection"):
        if values.get(field) is None:
            values.pop(field, None)
    canonical = json.dumps(
        {"action": action, "payload": values},
        sort_keys=True,
        separators=(",", ":"),
    )
    return IdempotencyRequest(
        key=key,
        action=action,
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        respond=lambda result: (status_code, jsonable_encoder(to_body(result))),
    )


def run_idempotent_write(operation_name, func, *args, idempotency, **kwargs):
    try:
        result = func(*args, idempotency=idempotency, **kwargs)

    except IdempotentReplay as replay:
        return JSONResponse(
            status_code=replay.status_code,
            content=replay.body,
            headers={"Idempotent-Replayed": "true"},
        )

    except PulseCaptureError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    except Exception as error:
        log_operation_failure("hmi_capture", operation_name, error)
        raise safe_503()

    status_code, body = idempotency.respond(result)
    return JSONResponse(status_code=status_code, content=body)
