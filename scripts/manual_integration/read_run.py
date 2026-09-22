"""
Manual live integration script (NOT a pytest test): recovers the
active production run on the real "Rovema" line from the live Supabase
database via recover_production_run(), printing the result. Read-only.

Never runs automatically - execute directly:
    python scripts/manual_integration/read_run.py
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

from src.main import recover_production_run
from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "read_run.py",
        "Read-only: recovers the active production run on the real 'Rovema' line.",
    )

    recovered_run = recover_production_run("Rovema")

    print("\n=== RECOVERED PULSE RUN ===")
    print(recovered_run)

    if recovered_run is not None:
        print("\n=== RECOVERY CHECK ===")
        print(f"Run ID: {recovered_run['database_run_id']}")
        print(f"Line: {recovered_run['production_line']}")
        print(f"Customer: {recovered_run['customer']}")
        print(f"Product: {recovered_run['product']}")
        print(f"Pallets Remaining: {recovered_run['pallets_remaining']}")
        print(f"Open Faults: {len(recovered_run['open_faults'])}")
        print(f"Next Fault ID: {recovered_run['next_fault_id']}")

        for fault in recovered_run["open_faults"]:
            print(
                f"Fault {fault['fault_id']}: "
                f"{fault['machine']} - {fault['reason']}"
            )


if __name__ == "__main__":
    run()
