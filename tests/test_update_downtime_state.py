from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    update_downtime_event_state,
    get_open_faults,
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