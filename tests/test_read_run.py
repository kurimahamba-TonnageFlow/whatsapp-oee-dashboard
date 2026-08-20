from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.main import recover_production_run


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