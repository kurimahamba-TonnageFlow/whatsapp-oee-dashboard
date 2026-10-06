# ==========================================================
# TONNAGEFLOW PULSE
# Server error logging
# ==========================================================
#
# One place that records why an API request failed, for whoever runs
# the server. A line says which area and operation failed and the
# exception's type and PostgreSQL SQLSTATE (e.g. 08006 connection
# failure, 23505 unique violation, 42P01 missing table). It never logs
# the exception message, arguments or traceback: psycopg messages can
# carry the database host and user, and row values, and nothing here
# may reach the client either (every caller answers with a pre-written
# 503).

import logging
import sys

logger = logging.getLogger("pulse.api")

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    # uvicorn configures its own loggers; keep Pulse lines out of them
    # so each failure is written once.
    logger.propagate = False


def describe_error(error):
    """Safe fields only: never str(error)."""
    error_type = type(error)
    return {
        "error_type": f"{error_type.__module__}.{error_type.__qualname__}",
        "sqlstate": getattr(error, "sqlstate", None) or "-",
    }


def log_operation_failure(area, operation_name, error):
    fields = describe_error(error)
    logger.error(
        "DATABASE ERROR area=%s operation=%s error_type=%s sqlstate=%s",
        area,
        operation_name,
        fields["error_type"],
        fields["sqlstate"],
    )
