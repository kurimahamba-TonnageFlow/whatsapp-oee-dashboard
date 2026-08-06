# TonnageFlow Pulse - Hourly Production Update


def welcome():
    print("===================================")
    print("       TonnageFlow Pulse")
    print("    Hourly Production Update")
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


def collect_hourly_update():
    production_line = input("Enter Production Line: ")

    available_technicians = line_technicians_by_line.get(
        production_line,
        [],
    )

    if available_technicians:
        print(
            "Line Technicians:",
            ", ".join(available_technicians),
        )
    else:
        print("Warning: Production line not recognised.")

    line_technician = input("Enter Line Technician: ")
    shift = input("Enter Shift: ")
    customer = input("Enter Customer: ")

    oee = float(input("Enter OEE (%): "))

    completed_pallets = int(
        input("Enter Pallets Completed: ")
    )

    planned_downtime = input(
        "Enter Planned Downtime or None: "
    )

    unplanned_downtime = input(
        "Enter Unplanned Downtime or None: "
    )

    engineer_called = "No"

    if unplanned_downtime.lower() != "none":
        engineer_called = input(
            "Has an engineer been called? (Yes/No): "
        )

    return (
        production_line,
        line_technician,
        shift,
        customer,
        oee,
        completed_pallets,
        planned_downtime,
        unplanned_downtime,
        engineer_called,
    )


welcome()


(
    production_line,
    line_technician,
    shift,
    customer,
    oee,
    completed_pallets,
    planned_downtime,
    unplanned_downtime,
    engineer_called,
) = collect_hourly_update()


print()
print("=== Hourly Production Update ===")
print(f"Production Line: {production_line}")
print(f"Line Technician: {line_technician}")
print(f"Shift: {shift}")
print(f"Customer: {customer}")
print(f"OEE: {oee}%")
print(f"Pallets Completed: {completed_pallets}")
print(f"Planned Downtime: {planned_downtime}")
print(f"Unplanned Downtime: {unplanned_downtime}")
print(f"Engineer Called: {engineer_called}")


if oee < 60:
    print(
        "Warning: Low OEE - Investigate immediately."
    )


if (
    unplanned_downtime.lower() != "none"
    and engineer_called.lower() == "yes"
):
    print(
        "Engineering response required. "
        "Awaiting engineering update."
    )


print()
print(
    "Planned Downtime Types:",
    ", ".join(planned_downtime_types),
)

print(
    "Available Engineers:",
    ", ".join(engineers),
)