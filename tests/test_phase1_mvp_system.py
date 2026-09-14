"""
Phase 1 MVP system verification.

Proves the existing Pulse engine can observe and persist one realistic
production journey end-to-end, using the real application functions
(start_production_run, collect_hourly_update, verify_open_faults,
ensure_engineer_called, capture_engineering_update, report_machine_down,
update_run_progress, save_hourly_update, persist_run_progress,
handle_run_completion, close_production_run, recover_production_run,
get_active_production_run, get_open_faults) against Supabase.

Uses the real, configured GIC production line and its real pack sizes -
not a synthetic line - since this is a system-level MVP proof, not an
isolated unit test. GIC's only prior TEST run (id 11) was verified and
closed as an explicit, separately-authorised prerequisite before this
file was written; Rovema (production_run_id 10) is never touched.

run_session() itself is not called directly: it is an interactive,
unbounded loop with no hook for "discard the in-memory run and recover
it", which this journey explicitly requires (step 12). Instead, this
test calls the same real functions run_session() calls, in the same
order and with the same data shape, so the restart can be simulated by
simply dropping the Python `run` dict and recovering a fresh one.
"""

import builtins
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import main
from src.database import (
    save_hourly_update,
    get_database_connection,
    get_active_production_run,
    get_open_faults,
)
from psycopg.rows import dict_row


PRODUCTION_LINE = "GIC"


# ==========================================================
# TEST HELPERS
# ==========================================================


def fetch_run(production_run_id):
    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.production_runs WHERE id = %s;",
                (production_run_id,),
            )
            return cursor.fetchone()


def fetch_hourly_updates(production_run_id):
    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.hourly_updates "
                "WHERE production_run_id = %s ORDER BY id;",
                (production_run_id,),
            )
            return cursor.fetchall()


def fetch_downtime_event(downtime_event_id):
    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.downtime_events WHERE id = %s;",
                (downtime_event_id,),
            )
            return cursor.fetchone()


def fetch_engineering_updates(downtime_event_id):
    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.engineering_updates "
                "WHERE downtime_event_id = %s ORDER BY id;",
                (downtime_event_id,),
            )
            return cursor.fetchall()


def checkpoint(label, expected, actual):
    ok = expected == actual
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")
    if not ok:
        raise AssertionError(f"CHECKPOINT FAILED: {label}")


class ScriptedInput:
    def __init__(self):
        self.queue = []

    def extend(self, *answers):
        self.queue.extend(answers)
        return self

    def __call__(self, prompt=""):
        if not self.queue:
            raise AssertionError(f"Ran out of scripted answers at prompt: {prompt!r}")
        value = self.queue.pop(0)
        print(f"{prompt}{value}")
        return value


scripted_input = ScriptedInput()
builtins.input = scripted_input


def apply_hourly_cycle(run, label):
    """Faithfully replicates run_session()'s hourly-update branch:
    collect_hourly_update() -> record events -> calculate performance
    -> check unexplained loss -> update in-memory progress -> save
    Hourly Update history -> persist the Production Run snapshot."""
    hourly_update = main.collect_hourly_update(run)

    main.record_event(
        run,
        "Hourly Update",
        "Hourly Update Received",
        run["line_technician"],
        oee=hourly_update["oee"],
        pallets_completed=hourly_update["pallets_completed_this_hour"],
    )

    if hourly_update["planned_downtime"] != "None":
        main.record_event(
            run,
            "Planned Downtime",
            hourly_update["planned_downtime"],
            run["line_technician"],
        )

    hour_performance = main.calculate_hour_performance(run, hourly_update)

    main.check_unexplained_production_loss(run, hourly_update, hour_performance)

    main.update_run_progress(run, hourly_update)

    database_hourly_update = {
        "production_run_id": run["database_run_id"],
        "oee": hourly_update["oee"],
        "pallets_completed": hourly_update["pallets_completed_this_hour"],
        "planned_downtime": hourly_update["planned_downtime"],
        "expected_packs": hour_performance["expected_packs"],
        "actual_packs": hour_performance["actual_packs"],
        "expected_pallets": hour_performance["expected_pallets"],
        "actual_pallets": hour_performance["actual_pallets"],
        "production_variance_packs": hour_performance["production_variance_packs"],
        "estimated_lost_packs": hour_performance["lost_packs"],
        "estimated_lost_minutes": hour_performance["estimated_lost_minutes"],
        "unexplained_loss": hourly_update["unexplained_loss"],
        "unexplained_loss_reason": hourly_update["unexplained_loss_reason"],
        "pallets_remaining": run["pallets_remaining"],
    }

    save_hourly_update(database_hourly_update)

    progress_saved = main.persist_run_progress(run)
    checkpoint(f"{label}: progress snapshot saved", True, progress_saved)

    main.display_hourly_report(run, hourly_update, hour_performance)

    return hourly_update, hour_performance


# ==========================================================
# STAGE 1: PRODUCTION RUN STARTS -> SETUP PERSISTS
# ==========================================================

scripted_input.extend(
    "GIC",                            # Select Production Line
    "Marina",                         # Select Line Technician
    "TEST-SHIFT",                     # Shift
    "TEST-PHASE1-MVP-SYSTEM",         # Customer
    "TEST-PRODUCT-DO-NOT-USE",        # Product
    "1kg",                            # Pack Size
    "10",                             # Packs per Case
    "TEST-PACK-TYPE",                 # Pack Type
    "8.4",                            # Target Speed ppm
    "10",                             # Cases per Pallet
    "25",                             # Pallets Remaining on Job
    "0",                              # Previous Run Pallets Completed
    "yes",                            # Confirm setup
)

run = main.start_production_run()
assert run is not None, "Production Run failed to start / save to Supabase"

production_run_id = run["database_run_id"]
print(f"Test production_run_id = {production_run_id}")

setup_row = fetch_run(production_run_id)
checkpoint("Setup persisted: production_line", "GIC", setup_row["production_line"])
checkpoint("Setup persisted: customer", "TEST-PHASE1-MVP-SYSTEM", setup_row["customer"])
checkpoint("Setup persisted: status", "Active", setup_row["status"])
checkpoint("Setup persisted: starting_pallets_remaining", 25, setup_row["starting_pallets_remaining"])


# ==========================================================
# STAGE 2: HOUR 1 AND HOUR 2 (no faults open yet)
# ==========================================================

scripted_input.extend("80.0", "5", "None", "no")   # oee, pallets, planned_downtime, retrospective
apply_hourly_cycle(run, "Hour 1")
checkpoint("Hour 1: pallets_remaining", 20, run["pallets_remaining"])
checkpoint("Hour 1: total_pallets_completed", 5, run["total_pallets_completed"])

scripted_input.extend("80.0", "5", "None", "no")
apply_hourly_cycle(run, "Hour 2")
checkpoint("Hour 2: pallets_remaining", 15, run["pallets_remaining"])
checkpoint("Hour 2: total_pallets_completed", 10, run["total_pallets_completed"])


# ==========================================================
# STAGE 3: UNPLANNED DOWNTIME IS REPORTED
# ==========================================================

scripted_input.extend(
    "TEST-MACHINE",     # Machine / Area
    "TEST-REASON",       # Reason
    "no",                 # Has an Engineer Been Called?
)

main.report_machine_down(run)

checkpoint("Fault opened", 1, len(run["open_faults"]))
fault = run["open_faults"][0]
downtime_event_id = fault["database_downtime_event_id"]
fault_id = fault["fault_id"]
print(f"Test downtime_event_id = {downtime_event_id}")
print(f"Test fault_id = {fault_id}")

initial_fault_row = fetch_downtime_event(downtime_event_id)
checkpoint("Downtime event: production_status", "Ongoing", initial_fault_row["production_status"])
checkpoint("Downtime event: resolved_at", None, initial_fault_row["resolved_at"])
checkpoint("Downtime event: engineer_called", False, initial_fault_row["engineer_called"])
checkpoint("Downtime event: linked to correct production_run_id", production_run_id, initial_fault_row["production_run_id"])


# ==========================================================
# STAGE 4: ENGINEER CALLED + ENGINEERING INITIAL RESPONSE
# (round 1 of fault verification, folded into an hourly cycle)
# ==========================================================

scripted_input.extend(
    "80.0", "0", "None",              # oee, pallets(0 - machine down), planned_downtime
    "ongoing",                          # Line Technician Fault Status
    "yes",                               # Has an Engineer now been called?
    "Aaron",                             # Select Engineer
    "TEST-FINDING-1",                    # Initial Finding
    "TEST-ACTION-1",                     # Action / Investigation
    "ongoing",                           # Engineering Status
    "no",                                # retrospective downtime
)
apply_hourly_cycle(run, "Fault round 1 (engineer called + initial response)")

round1_row = fetch_downtime_event(downtime_event_id)
checkpoint("Round 1: engineer_called persisted", True, round1_row["engineer_called"])
checkpoint("Round 1: engineer persisted", "Aaron", round1_row["engineer"])
checkpoint("Round 1: engineering_status persisted", "Ongoing", round1_row["engineering_status"])
checkpoint("Round 1: production_status unaffected", "Ongoing", round1_row["production_status"])

round1_updates = fetch_engineering_updates(downtime_event_id)
checkpoint("Round 1: engineering_updates row count", 1, len(round1_updates))
checkpoint("Round 1: engineering_update linked to correct event", downtime_event_id, round1_updates[0]["downtime_event_id"])
checkpoint("Round 1: engineering_update linked to correct run", production_run_id, round1_updates[0]["production_run_id"])
checkpoint("Round 1: engineering_update linked to correct fault_id", fault_id, round1_updates[0]["fault_id"])
checkpoint("Round 1: engineering_update type", "Investigation", round1_updates[0]["update_type"])


# ==========================================================
# STAGE 5: ENGINEERING MARKS ITS WORK RESOLVED
# (must NOT resolve production - round 2)
# ==========================================================

scripted_input.extend(
    "80.0", "0", "None",
    "ongoing",                           # technician still says ongoing
    "Aaron",
    "TEST-STILL-ONGOING",
    "TEST-ACTION-2",
    "resolved",                          # Engineering marks itself resolved
    "no",
)
apply_hourly_cycle(run, "Fault round 2 (engineering resolves)")

round2_row = fetch_downtime_event(downtime_event_id)
checkpoint("Round 2: engineering_status = Resolved", "Resolved", round2_row["engineering_status"])
checkpoint("Round 2: production_status NOT auto-resolved", "Ongoing", round2_row["production_status"])
checkpoint("Round 2: resolved_at NOT set by engineering alone", None, round2_row["resolved_at"])

round2_updates = fetch_engineering_updates(downtime_event_id)
checkpoint("Round 2: engineering_updates row count", 2, len(round2_updates))
checkpoint("Round 2: engineering_update type", "Resolution", round2_updates[1]["update_type"])

checkpoint("Fault still open before technician confirmation", 1, len(run["open_faults"]))


# ==========================================================
# STAGE 6: TECHNICIAN CONFIRMS PRODUCTION FAULT RESOLVED
# ==========================================================

scripted_input.extend(
    "80.0", "0", "None",
    "resolved",                          # Line Technician confirms Resolved
    "no",
)
apply_hourly_cycle(run, "Fault round 3 (technician resolves)")

checkpoint("Fault removed from in-memory open_faults", 0, len(run["open_faults"]))

final_fault_row = fetch_downtime_event(downtime_event_id)
checkpoint("Final production_status", "Resolved", final_fault_row["production_status"])
checkpoint("Final resolved_at is a real timestamp", True, final_fault_row["resolved_at"] is not None)


# ==========================================================
# STAGE 7: FAULT DISAPPEARS FROM OPEN FAULTS, STAYS IN HISTORY
# ==========================================================

open_faults_now = get_open_faults(production_run_id)
checkpoint("get_open_faults excludes resolved fault", 0, len(open_faults_now))

history_row = fetch_downtime_event(downtime_event_id)
checkpoint("downtime_events history row still exists", True, history_row is not None)


# ==========================================================
# STAGE 8: HOUR 3 (clean, no open faults)
# ==========================================================

scripted_input.extend("80.0", "5", "None", "no")
apply_hourly_cycle(run, "Hour 3")
checkpoint("Hour 3: pallets_remaining", 10, run["pallets_remaining"])
checkpoint("Hour 3: total_pallets_completed", 15, run["total_pallets_completed"])

pre_restart_row = fetch_run(production_run_id)
checkpoint("Pre-restart DB pallets_remaining", 10, pre_restart_row["pallets_remaining"])
checkpoint("Pre-restart DB total_pallets_completed", 15, pre_restart_row["total_pallets_completed"])


# ==========================================================
# STAGE 9-10: DISCARD IN-MEMORY RUN -> RECOVER FROM SUPABASE
# ==========================================================

del run   # simulate the process being gone - nothing left to reuse

recovered = main.recover_production_run(PRODUCTION_LINE)
assert recovered is not None, "Recovery failed to find the TEST run"

checkpoint("Recovered run is the correct run", production_run_id, recovered["database_run_id"])
checkpoint("Recovered pallets_remaining", 10, recovered["pallets_remaining"])
checkpoint("Recovered total_pallets_completed", 15, recovered["total_pallets_completed"])
checkpoint("Recovered potential_overrun_pallets", 0, recovered["potential_overrun_pallets"])
checkpoint("Recovered confirmed_overrun_pallets", 0, recovered["confirmed_overrun_pallets"])
checkpoint("Recovered open_faults is empty", 0, len(recovered["open_faults"]))
checkpoint("Recovered events list present", [], recovered["events"])
checkpoint("Recovered pack_weight reconstructed", "1kg", recovered["pack_weight"])


# ==========================================================
# STAGE 11: HOUR 4 ON THE RECOVERED RUN - NO DOUBLE-COUNTING
# A stale recovery (remaining stuck at 25) would produce
# remaining=20/total=10 here instead of 5/20.
# ==========================================================

scripted_input.extend("80.0", "5", "None", "no")
apply_hourly_cycle(recovered, "Hour 4 (post-recovery)")
checkpoint("Hour 4: pallets_remaining (no double-count)", 5, recovered["pallets_remaining"])
checkpoint("Hour 4: total_pallets_completed (no double-count)", 20, recovered["total_pallets_completed"])

post_hour4_row = fetch_run(production_run_id)
checkpoint("DB pallets_remaining after Hour 4", 5, post_hour4_row["pallets_remaining"])
checkpoint("DB total_pallets_completed after Hour 4", 20, post_hour4_row["total_pallets_completed"])


# ==========================================================
# STAGE 12: FINISH THE RUN - REAL CUSTOMER CHANGEOVER PATH
# ==========================================================

scripted_input.extend("Customer Changeover")
main.handle_run_completion(recovered)
checkpoint("Changeover type recorded", "Customer Changeover", recovered["changeover_type"])
checkpoint("confirmed_overrun_pallets after changeover", 0, recovered["confirmed_overrun_pallets"])


# ==========================================================
# STAGE 13: FINAL CLOSURE GATE (mirrors run_session() exactly)
# ==========================================================

final_progress_saved = main.persist_run_progress(recovered)
checkpoint("Final progress persistence succeeded", True, final_progress_saved)

closed_id = main.close_production_run(recovered["database_run_id"], main.current_timestamp())
checkpoint("close_production_run returns the correct id", production_run_id, closed_id)


# ==========================================================
# STAGE 14: RUN BECOMES COMPLETED, finished_at POPULATED
# ==========================================================

closed_row = fetch_run(production_run_id)
checkpoint("DB status is Completed", "Completed", closed_row["status"])
checkpoint("DB finished_at is set", True, closed_row["finished_at"] is not None)
checkpoint("DB finished_at >= started_at", True, closed_row["finished_at"] >= closed_row["started_at"])
checkpoint("Final pallets_remaining preserved", 5, closed_row["pallets_remaining"])
checkpoint("Final total_pallets_completed preserved", 20, closed_row["total_pallets_completed"])
checkpoint("Final potential_overrun_pallets preserved", 0, closed_row["potential_overrun_pallets"])
checkpoint("Final confirmed_overrun_pallets preserved", 0, closed_row["confirmed_overrun_pallets"])


# ==========================================================
# STAGE 15: COMPLETED RUN CANNOT RECOVER AS ACTIVE
# ==========================================================

checkpoint("get_active_production_run returns None", None, get_active_production_run(PRODUCTION_LINE))
checkpoint("recover_production_run returns None", None, main.recover_production_run(PRODUCTION_LINE))


# ==========================================================
# STAGE 16: SECOND PRODUCTION RUN STARTS ON THE SAME GIC LINE
# ==========================================================

scripted_input.extend(
    "GIC",
    "Mariusz",
    "TEST-SHIFT-2",
    "TEST-PHASE1-MVP-SYSTEM-2",
    "TEST-PRODUCT-DO-NOT-USE",
    "4kg",
    "8",
    "TEST-PACK-TYPE",
    "10",
    "8",
    "12",
    "0",
    "yes",
)

second_run = main.start_production_run()
assert second_run is not None, "Second Production Run failed to start"
second_production_run_id = second_run["database_run_id"]
print(f"Second test production_run_id = {second_production_run_id}")


# ==========================================================
# STAGE 17: EXACTLY ONE ACTIVE RUN EXISTS ON GIC
# ==========================================================

with get_database_connection() as connection:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT id FROM public.production_runs "
            "WHERE production_line = %s AND status = 'Active';",
            (PRODUCTION_LINE,),
        )
        active_gic_runs = cursor.fetchall()

checkpoint("Exactly one Active run on GIC", 1, len(active_gic_runs))
checkpoint("That run is the second run", second_production_run_id, active_gic_runs[0]["id"])


# ==========================================================
# STAGE 18: FIRST RUN REMAINS HISTORICAL
# ==========================================================

first_run_history = fetch_run(production_run_id)
checkpoint("First run still exists", True, first_run_history is not None)
checkpoint("First run still shows Completed", "Completed", first_run_history["status"])

first_run_hourly_history = fetch_hourly_updates(production_run_id)
checkpoint("First run's Hourly Update history intact", 7, len(first_run_hourly_history))

first_run_fault_history = fetch_downtime_event(downtime_event_id)
checkpoint("First run's downtime event still exists", True, first_run_fault_history is not None)

first_run_engineering_history = fetch_engineering_updates(downtime_event_id)
checkpoint("First run's engineering history intact", 2, len(first_run_engineering_history))


print()
print("=== ALL CHECKPOINTS PASSED ===")
print(f"first production_run_id (Completed) = {production_run_id}")
print(f"second production_run_id (Active) = {second_production_run_id}")
print(f"downtime_event_id = {downtime_event_id}")
print(f"fault_id = {fault_id}")
