# ==========================================================
# TONNAGEFLOW PULSE
# Readiness check
# ==========================================================
#
# GET /health        - liveness: the process answers (whatsapp_webhook.py,
#                      unchanged, no database call).
# GET /health/ready  - readiness: the database answers AND has the
#                      schema this code needs, including standards and task observations.
#                      Use it for the deploy smoke test and any uptime
#                      monitor. 200 when ready, 503 when not; the body
#                      never contains connection details or error text.

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from .api_logging import log_operation_failure
    from .database import check_schema_readiness
except ImportError:
    from api_logging import log_operation_failure
    from database import check_schema_readiness

router = APIRouter(tags=["health"])


@router.get("/health/ready")
def readiness():
    try:
        markers = check_schema_readiness()

    except Exception as error:
        log_operation_failure("health", "readiness", error)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )

    missing = sorted(migration for migration, present in markers.items() if not present)

    if missing:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "ok", "missing_migrations": missing},
        )

    return {"status": "ready", "database": "ok", "missing_migrations": []}
