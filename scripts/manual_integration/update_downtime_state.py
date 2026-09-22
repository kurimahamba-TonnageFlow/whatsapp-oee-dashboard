"""
Manual live integration script (NOT a pytest test): updates one real
downtime_events row (hardcoded downtime_event_id=2) via
update_downtime_event_state(), then reads back open faults. Performs a
real UPDATE against the live Supabase database.

Never runs automatically - execute directly:
    python scripts/manual_integration/update_downtime_state.py
after setting the required confirmation environment variable (see
_safety.require_live_confirmation). Importing this module has no side
effects; all execution lives inside run(), called only from the
__main__ guard below.
"""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    update_downtime_event_state,
    get_open_faults,
)
from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "update_downtime_state.py",
        "Updates one real downtime_events row (hardcoded downtime_event_id=2, "
        "engineer='Aaron'), then reads back open faults.",
    )

    updated_id = update_downtime_event_state(
        downtime_event_id=2,
        engineer_called=True,
        production_status="Ongoing",
        engineering_status="Ongoing",
        engineer="Aaron",
    )

    print(f"Updated Downtime Event ID: {updated_id}")

    open_faults = get_open_faults(10)

    print("\n=== DATABASE STATE ===")

    for fault in open_faults:
        print(f"Fault ID: {fault['fault_id']}")
        print(f"Machine: {fault['machine']}")
        print(f"Engineer Called: {fault['engineer_called']}")
        print(f"Engineering Status: {fault['engineering_status']}")
        print(f"Engineer: {fault['engineer']}")
        print(f"Production Status: {fault['production_status']}")
        print(f"Resolved At: {fault['resolved_at']}")


if __name__ == "__main__":
    run()
