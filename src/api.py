# ==========================================================
# TONNAGEFLOW PULSE
# Main HTTP API (HMI + WhatsApp)
# ==========================================================
#
# This is the process to run with uvicorn. It:
#   - Adds the versioned Production Run API (src/runs_api.py)
#   - Restricts CORS to the exact Pulse HMI origin (no wildcard)
#   - Mounts the existing, unmodified WhatsApp webhook app at "/" so
#     every route in src/whatsapp_webhook.py keeps working exactly as
#     it does today, including for its own existing test suite, which
#     imports that app directly and never touches this module.
#
# src/main.py (the CLI engine) is never imported here.

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .dashboard_api import router as dashboard_router
    from .hmi_config_api import router as hmi_config_router
    from .management_api import router as management_router
    from .runs_api import router as runs_router
    from .whatsapp_webhook import app as whatsapp_app
except ImportError:
    from dashboard_api import router as dashboard_router
    from hmi_config_api import router as hmi_config_router
    from management_api import router as management_router
    from runs_api import router as runs_router
    from whatsapp_webhook import app as whatsapp_app

load_dotenv()


# ==========================================================
# CORS
# ==========================================================
# Exactly two allowed origins - the deployed Pulse HMI and the deployed
# Pulse Dashboard. Never widen this to "*"; override HMI_ORIGIN /
# DASHBOARD_ORIGIN in the environment if either one ever moves.

HMI_ORIGIN = os.getenv(
    "HMI_ORIGIN",
    "https://tonnage-flow-pulse-hmi.kurirai-mahamba.chatgpt.site",
)

DASHBOARD_ORIGIN = os.getenv(
    "DASHBOARD_ORIGIN",
    "https://tonnage-flow-pulse-dashboard.kurirai-mahamba.chatgpt.site",
)


app = FastAPI(title="TonnageFlow Pulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[HMI_ORIGIN, DASHBOARD_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ==========================================================
# ROUTES
# ==========================================================

app.include_router(dashboard_router)
app.include_router(runs_router)
app.include_router(management_router)
app.include_router(hmi_config_router)

# Mounted last, at root, so the explicit routes above always take
# priority; every other path (including /health and /webhooks/whatsapp)
# falls through to the existing WhatsApp app unchanged.
app.mount("/", whatsapp_app)
