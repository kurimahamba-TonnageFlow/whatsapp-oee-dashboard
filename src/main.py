# TonnageFlow Pulse - Hourly Production Update

oee = input("Enter OEE (%): ")

completed_pallets = input("Enter Pallets Completed: ")

customer = input("Enter Customer: ")

shift = input("Enter Shift: ")

production_line = input("Enter Production Line: ")

engineer = input("Enter Engineer: ")

engineers = [
    "Aaron",
    "Yago",
    "Steve",
    "Dan",
    "Kuri"
]

production_lines = [
    "Rovema",
    "GIC",
    "Guill"
]

planned_downtime = [
    "Label Change",
    "Film Change",
    "CCP Check",
    "Changeover"
]

unplanned_downtime = [
    "Casepacker Jam",
    "Conveyor Stop",
    "Machine Fault"
]

print("=== TonnageFlow Pulse ===")
print(f"OEE: {oee}%")
print(f"Pallets Completed: {completed_pallets}")
print(f"Customer: {customer}")
print(f"Shift: {shift}")
print(f"Production Line: {production_line}")
print(f"Engineer: {engineer}")

print("Available Engineers:", ", ".join(engineers))
print("Available Production Lines:", ", ".join(production_lines))
print("Planned Downtime:", ", ".join(planned_downtime))
print("Unplanned Downtime:", ", ".join(unplanned_downtime))