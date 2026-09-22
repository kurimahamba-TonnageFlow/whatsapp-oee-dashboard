"""
Manual live integration script (NOT a pytest test): inserts one real
hourly_updates row into the live Supabase database using a hardcoded
production_run_id, to manually verify save_hourly_update() end to end.

Never runs automatically - execute directly:
    python scripts/manual_integration/hourly_update.py
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

from src.database import save_hourly_update
from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "hourly_update.py",
        "Inserts one real hourly_updates row (hardcoded production_run_id=2) "
        "with no cleanup.",
    )

    test_update = {
        "production_run_id": 2,
        "oee": 78.0,
        "pallets_completed": 3,
        "planned_downtime": "None",
        "expected_packs": 7200,
        "actual_packs": 5280,
        "expected_pallets": 4.09,
        "actual_pallets": 3,
        "production_variance_packs": -1920,
        "estimated_lost_packs": 1920,
        "estimated_lost_minutes": 16.0,
        "unexplained_loss": False,
        "unexplained_loss_reason": None,
        "pallets_remaining": 35,
    }

    hourly_update_id = save_hourly_update(
        test_update
    )

    print(
        "Hourly Update saved successfully."
    )

    print(
        f"Hourly Update ID: "
        f"{hourly_update_id}"
    )


if __name__ == "__main__":
    run()
