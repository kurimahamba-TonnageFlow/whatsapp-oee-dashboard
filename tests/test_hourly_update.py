from src.database import save_hourly_update


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