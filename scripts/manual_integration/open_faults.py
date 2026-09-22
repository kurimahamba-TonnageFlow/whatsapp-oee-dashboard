"""
Manual live integration script (NOT a pytest test): reads open faults
for a hardcoded production_run_id from the live Supabase database via
get_open_faults() and build_fault_from_database(), printing the
result. Read-only.

Never runs automatically - execute directly:
    python scripts/manual_integration/open_faults.py
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

from src.database import get_open_faults
from src.main import build_fault_from_database
from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "open_faults.py",
        "Read-only: fetches open faults for hardcoded production_run_id=10.",
    )

    database_faults = get_open_faults(10)

    pulse_faults = [
        build_fault_from_database(fault)
        for fault in database_faults
    ]

    print(pulse_faults)


if __name__ == "__main__":
    run()
