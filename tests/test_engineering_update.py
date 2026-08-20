from src.database import save_engineering_update


test_update = {
    "downtime_event_id": 1,
    "production_run_id": 3,
    "fault_id": 1,
    "engineer": "Aaron",
    "update_type": "Investigation",
    "finding": "Casepacker sensor appears misaligned",
    "action": "Sensor checked and adjusted",
    "engineering_status": "Ongoing",
}


engineering_update_id = save_engineering_update(
    test_update
)


print(
    "Engineering Update saved successfully."
)

print(
    f"Engineering Update ID: "
    f"{engineering_update_id}"
)