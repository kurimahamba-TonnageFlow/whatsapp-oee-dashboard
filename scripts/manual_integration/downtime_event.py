"""
Manual live integration script (NOT a pytest test): inserts one real
downtime_events row into the live Supabase database using a hardcoded
production_run_id, to manually verify save_downtime_event() end to end.

Never runs automatically - execute directly:
    python scripts/manual_integration/downtime_event.py
after setting the required confirmation environment variable (see
_safety.require_live_confirmation). Importing this module has no side
effects; all execution lives inside run(), called only from the
__main__ guard below.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import save_downtime_event
from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "downtime_event.py",
        "Inserts one real downtime_events row (hardcoded production_run_id=3, "
        "engineer='Aaron') with no cleanup.",
    )

    test_event = {
        "production_run_id": 3,
        "fault_id": 1,
        "machine": "Casepacker",
        "reason": "Open cases",
        "reported_by": "Liam",
        "engineer_called": True,
        "production_status": "Ongoing",
        "engineering_status": "Ongoing",
        "engineer": "Aaron",
        "retrospective": False,
        "opened_at": datetime.now(timezone.utc),
        "resolved_at": None,
    }

    downtime_event_id = save_downtime_event(
        test_event
    )

    print(
        "Downtime Event saved successfully."
    )

    print(
        f"Downtime Event ID: {downtime_event_id}"
    )


if __name__ == "__main__":
    run()
