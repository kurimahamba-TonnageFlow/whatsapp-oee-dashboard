# ==========================================================
# TONNAGEFLOW PULSE
# Public HMI Configuration
# ==========================================================
#
# Read-only, no authentication. Returns only active lines, machines
# and buttons - never Management data (audit log, sessions, disabled
# rows) or credentials. The operator HMI polls this so newly added
# buttons appear after a refresh without republishing the HMI.

from fastapi import APIRouter, HTTPException

try:
    from .database import get_public_hmi_config
except ImportError:
    from database import get_public_hmi_config


router = APIRouter(prefix="/api/v1/hmi", tags=["hmi-config"])


def _assemble_config_tree(rows):
    lines_by_id = {}
    line_order = []

    for row in rows:
        line_id = row["line_id"]

        if line_id not in lines_by_id:
            lines_by_id[line_id] = {
                "id": line_id,
                "name": row["line_name"],
                "machines": {},
            }
            line_order.append(line_id)

        line = lines_by_id[line_id]
        machine_id = row["machine_id"]

        if machine_id is None:
            continue

        if machine_id not in line["machines"]:
            line["machines"][machine_id] = {
                "id": machine_id,
                "name": row["machine_name"],
                "buttons": [],
            }

        button_id = row["button_id"]

        if button_id is None:
            continue

        line["machines"][machine_id]["buttons"].append({
            "id": button_id,
            "name": row["button_name"],
            "event_type": row["event_type"],
            "ownership": row["ownership"],
            "fault_category": row["fault_category"],
        })

    return [
        {
            "id": lines_by_id[line_id]["id"],
            "name": lines_by_id[line_id]["name"],
            "machines": list(lines_by_id[line_id]["machines"].values()),
        }
        for line_id in line_order
    ]


@router.get("/config")
def hmi_config():
    try:
        rows = get_public_hmi_config()

    except Exception:
        print("DATABASE ERROR")
        print("Could not load HMI configuration.")

        raise HTTPException(
            status_code=503,
            detail="Could not load configuration. Please try again.",
        )

    return {"lines": _assemble_config_tree(rows)}
