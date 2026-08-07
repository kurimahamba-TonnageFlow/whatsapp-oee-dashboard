# TonnageFlow Pulse - Production Run Tracker


def welcome():
    print("===================================")
    print("       TonnageFlow Pulse")
    print("     Production Run Tracker")
    print("===================================")


line_technicians_by_line = {
    "Rovema": [
        "Rovema Technician 1",
        "Rovema Technician 2",
        "Rovema Technician 3",
        "Rovema Technician 4",
    ],
    "GIC": [
        "GIC Technician 1",
        "GIC Technician 2",
        "GIC Technician 3",
        "GIC Technician 4",
    ],
    "Guill": [
        "Guill Technician 1",
        "Guill Technician 2",
        "Guill Technician 3",
        "Guill Technician 4",
    ],
}


engineers = [
    "Aaron",
    "Yago",
    "Steve",
    "Dan",
    "Kuri",
]


planned_downtime_types = [
    "Label Change",
    "Film Change",
    "CCP Check",
    "Changeover",
]


def start_production_run():
    print()
    print("=== Start Production Run ===")

    production_line = input("Production Line: ")

    available_technicians = line_technicians_by_line.get(
        production_line,
        [],
    )

    if available_technicians:
        print(
            "Available Line Technicians:",
            ", ".join(available_technicians),
        )
    else:
        print("Warning: Production line not recognised.")

    line_technician = input("Line Technician: ")
    shift = input("Shift: ")
    customer = input("Customer: ")
    product = input("Product: ")

    pack_weight = input("Pack Weight (example 1kg): ")

    packs_per_case = int(
        input("Packs per Case (example 8): ")
    )

    pack_type = input(
        "Pack Type (example Pillow Pack): "
    )

    target_speed_ppm = float(
        input("Target Speed - Packs per Minute: ")
    )

    cases_per_pallet = int(
        input("Cases per Pallet: ")
    )

    pallets_remaining = int(
        input("Pallets Remaining on Job: ")
    )

    previous_run_completed = int(
        input("Previous Run Pallets Completed: ")
    )

    return {
        "production_line": production_line,
        "line_technician": line_technician,
        "shift": shift,
        "customer": customer,
        "product": product,
        "pack_weight": pack_weight,
        "packs_per_case": packs_per_case,
        "pack_type": pack_type,
        "target_speed_ppm": target_speed_ppm,
        "cases_per_pallet": cases_per_pallet,
        "pallets_remaining": pallets_remaining,
        "previous_run_completed": previous_run_completed,
        "total_pallets_completed": 0,
        "overrun_pallets": 0,
    }


def calculate_expected_output(run):
    expected_packs_per_hour = (
        run["target_speed_ppm"] * 60
    )

    expected_cases_per_hour = (
        expected_packs_per_hour
        / run["packs_per_case"]
    )

    expected_pallets_per_hour = (
        expected_cases_per_hour
        / run["cases_per_pallet"]
    )

    return (
        expected_packs_per_hour,
        expected_cases_per_hour,
        expected_pallets_per_hour,
    )


def collect_hourly_update(run):
    print()
    print("=== Hourly Production Update ===")

    oee = float(
        input("OEE (%): ")
    )

    pallets_completed_this_hour = int(
        input("Pallets Completed This Hour: ")
    )

    planned_downtime = input(
        "Planned Downtime or None: "
    )

    unplanned_downtime = input(
        "Unplanned Downtime or None: "
    )

    engineer_called = "Not Required"

    if unplanned_downtime.lower() != "none":
        engineer_called = input(
            "Has an Engineer Been Called? (Yes/No): "
        )

    return {
        "oee": oee,
        "pallets_completed_this_hour":
            pallets_completed_this_hour,
        "planned_downtime": planned_downtime,
        "unplanned_downtime":
            unplanned_downtime,
        "engineer_called": engineer_called,
    }


def calculate_hour_performance(run, hourly_update):
    (
        expected_packs,
        expected_cases,
        expected_pallets,
    ) = calculate_expected_output(run)

    actual_pallets = hourly_update[
        "pallets_completed_this_hour"
    ]

    actual_cases = (
        actual_pallets
        * run["cases_per_pallet"]
    )

    actual_packs = (
        actual_cases
        * run["packs_per_case"]
    )

    lost_packs = expected_packs - actual_packs

    if lost_packs < 0:
        lost_packs = 0

    estimated_lost_minutes = (
        lost_packs
        / run["target_speed_ppm"]
    )

    return {
        "expected_packs": expected_packs,
        "expected_cases": expected_cases,
        "expected_pallets": expected_pallets,
        "actual_packs": actual_packs,
        "actual_cases": actual_cases,
        "actual_pallets": actual_pallets,
        "lost_packs": lost_packs,
        "estimated_lost_minutes":
            estimated_lost_minutes,
    }


def update_run_progress(run, hourly_update):
    pallets_completed = hourly_update[
        "pallets_completed_this_hour"
    ]

    run["total_pallets_completed"] += (
        pallets_completed
    )

    run["pallets_remaining"] -= (
        pallets_completed
    )

    if run["pallets_remaining"] < 0:
        run["pallets_remaining"] = 0


def display_hourly_report(
    run,
    hourly_update,
    performance,
):
    print()
    print("=== TonnageFlow Pulse ===")

    print(
        f"Production Line: "
        f"{run['production_line']}"
    )

    print(
        f"Product: {run['product']}"
    )

    print(
        f"Format: "
        f"{run['pack_weight']} x "
        f"{run['packs_per_case']}"
    )

    print(
        f"Customer: {run['customer']}"
    )

    print(
        f"OEE: {hourly_update['oee']}%"
    )

    print(
        f"Pallets Completed This Hour: "
        f"{hourly_update['pallets_completed_this_hour']}"
    )

    print(
        f"Total Pallets Completed This Run: "
        f"{run['total_pallets_completed']}"
    )

    print(
        f"Pallets Remaining: "
        f"{run['pallets_remaining']}"
    )

    print()
    print("--- Expected vs Actual ---")

    print(
        f"Expected Packs This Hour: "
        f"{performance['expected_packs']:.0f}"
    )

    print(
        f"Actual Packs This Hour: "
        f"{performance['actual_packs']}"
    )

    print(
        f"Expected Pallets This Hour: "
        f"{performance['expected_pallets']:.2f}"
    )

    print(
        f"Actual Pallets This Hour: "
        f"{performance['actual_pallets']}"
    )

    print(
        f"Estimated Lost Packs: "
        f"{performance['lost_packs']:.0f}"
    )

    print(
        f"Estimated Lost Production Time: "
        f"{performance['estimated_lost_minutes']:.1f} minutes"
    )

    print()
    print(
        f"Planned Downtime: "
        f"{hourly_update['planned_downtime']}"
    )

    print(
        f"Unplanned Downtime: "
        f"{hourly_update['unplanned_downtime']}"
    )

    print(
        f"Engineer Called: "
        f"{hourly_update['engineer_called']}"
    )


def handle_run_completion(run):
    if run["pallets_remaining"] > 0:
        return

    print()
    print("=== Planned Job Quantity Complete ===")

    changeover_type = input(
        "Next run is Product Changeover "
        "or Customer Changeover? "
    )

    if changeover_type.lower() == "product changeover":

        extra_pallets = int(
            input(
                "Extra Pallets Produced "
                "While Emptying Product: "
            )
        )

        run["overrun_pallets"] = extra_pallets

        print()
        print("Product Changeover")
        print(
            f"Overrun Recorded: "
            f"{run['overrun_pallets']} Pallets"
        )

    elif changeover_type.lower() == "customer changeover":

        run["overrun_pallets"] = 0

        print()
        print("Customer Changeover")
        print("Same product continues.")
        print("No overrun recorded.")

    else:
        print(
            "Changeover type not recognised."
        )


welcome()

production_run = start_production_run()


(
    expected_packs,
    expected_cases,
    expected_pallets,
) = calculate_expected_output(
    production_run
)


print()
print("=== Production Model ===")

print(
    f"Expected Packs per Hour: "
    f"{expected_packs:.0f}"
)

print(
    f"Expected Cases per Hour: "
    f"{expected_cases:.0f}"
)

print(
    f"Expected Pallets per Hour: "
    f"{expected_pallets:.2f}"
)

print(
    f"Starting Pallets Remaining: "
    f"{production_run['pallets_remaining']}"
)


hourly_update = collect_hourly_update(
    production_run
)


hour_performance = calculate_hour_performance(
    production_run,
    hourly_update,
)


update_run_progress(
    production_run,
    hourly_update,
)


display_hourly_report(
    production_run,
    hourly_update,
    hour_performance,
)


handle_run_completion(
    production_run
)