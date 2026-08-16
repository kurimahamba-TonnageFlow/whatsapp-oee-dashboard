from datetime import datetime, timezone

from src.database import save_downtime_event


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