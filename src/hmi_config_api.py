# ==========================================================
# TONNAGEFLOW PULSE
# Public HMI Configuration
# ==========================================================
#
# Read-only, no authentication. Returns only active lines, machines
# and buttons - never Management data (audit log, sessions, disabled
# rows) or credentials. The operator HMI polls this so newly added
# buttons appear after a refresh without republishing the HMI.

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

try:
    from . import pulse_calculations as calc
    from .database import get_hmi_line_state, get_public_hmi_config
except ImportError:
    import pulse_calculations as calc
    from database import get_hmi_line_state, get_public_hmi_config


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


# ==========================================================
# CROSS-DEVICE LINE STATE
# ==========================================================
#
# The authoritative answer to "can this tablet start a run on this
# line?". Before this existed the Home screen could only see the run
# saved in its own localStorage, so a second tablet showed a line as
# available while it was already running. The database uniqueness
# constraint was - and remains - the final authority; this endpoint
# exists so the operator is told before they fill in a Start Run form,
# not after.
#
# Read-only and unauthenticated, like /config. It carries no
# Management-only information: no tonnage, achievement, OEE, target,
# waste or cost figure appears here.


def _now():
    return datetime.now(timezone.utc)


def _latest_activity(row):
    """The most recent thing the database actually recorded for this
    run. Legacy hourly updates with no timestamp contribute nothing
    rather than a guessed time."""
    candidates = [
        row.get("started_at"),
        row.get("last_hourly_update_at"),
        row.get("last_planned_downtime_at"),
        row.get("last_changeover_at"),
        row.get("last_fault_opened_at"),
    ]
    recorded = [moment for moment in candidates if moment is not None]

    return max(recorded) if recorded else None


def _line_state_api(row, now):
    run_id = row.get("run_id")
    has_active_run = run_id is not None

    if not has_active_run:
        freshness = calc.freshness(False, None, None, now)

        return {
            "line_id": row["line_id"],
            "production_line": row["line_name"],
            "has_active_run": False,
            "run_id": None,
            "line_technician": None,
            "shift": None,
            "customer": None,
            "product": None,
            "started_at": None,
            "planned_downtime_active": False,
            "changeover_active": False,
            "engineering_fault_open": False,
            "open_fault_count": 0,
            "last_activity_at": None,
            **freshness,
        }

    freshness = calc.freshness(
        True,
        row.get("last_hourly_update_at"),
        row.get("started_at"),
        now,
    )
    open_fault_count = int(row.get("open_fault_count") or 0)

    return {
        "line_id": row["line_id"],
        "production_line": row["line_name"],
        "has_active_run": True,
        "run_id": run_id,
        "line_technician": row.get("line_technician"),
        "shift": row.get("shift"),
        "customer": row.get("customer"),
        "product": row.get("product"),
        "started_at": row.get("started_at"),
        "planned_downtime_active": row.get("open_planned_downtime_id") is not None,
        "changeover_active": row.get("open_changeover_id") is not None,
        "engineering_fault_open": open_fault_count > 0,
        "open_fault_count": open_fault_count,
        "last_activity_at": _latest_activity(row),
        **freshness,
    }


@router.get("/lines")
def hmi_line_state():
    try:
        rows = get_hmi_line_state()

    except Exception:
        print("DATABASE ERROR")
        print("Could not load production line state.")

        raise HTTPException(
            status_code=503,
            detail="Could not load line status. Please try again.",
        )

    now = _now()

    return {
        "generated_at": now,
        "stale_after_minutes": calc.DEFAULT_STALE_AFTER_MINUTES,
        "lines": [_line_state_api(row, now) for row in rows],
    }
