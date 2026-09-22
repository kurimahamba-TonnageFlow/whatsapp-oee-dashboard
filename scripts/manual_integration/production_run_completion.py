"""
Manual live integration script (NOT a pytest test).

Proves the Production Run Completion lifecycle: a run is only ever marked
Completed after its final progress snapshot has safely persisted, the
completed run stops being "active", its history is preserved, and a new
run can then start on the same production line.

Uses the real update_run_progress(), save_hourly_update(),
persist_run_progress(), handle_run_completion(), close_production_run()
and recover_production_run() functions against Supabase.

Creates its own clearly-labelled TEST production runs on a synthetic,
test-only production line ("TEST-LINE-COMPLETION") rather than hard-coding
any shared production_run_id or reusing a real factory line - consistent
with production_run_progress.py in this same folder.

Never runs automatically - execute directly:
    python scripts/manual_integration/production_run_completion.py
after setting the required confirmation environment variable (see
_safety.require_live_confirmation). Importing this module has no side
effects (including builtins.input and pulse_main.pack_sizes_by_line,
only ever mutated inside run()); all execution lives inside run(),
called only from the __main__ guard below.
"""

import builtins
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src import main as pulse_main
from src.database import (
    save_production_run,
    save_hourly_update,
    get_database_connection,
    get_active_production_run,
)
from psycopg.rows import dict_row
from _safety import require_live_confirmation


PRODUCTION_LINE = "TEST-LINE-COMPLETION"
TEST_PACK_SIZE_LABEL = "1kg"
TEST_PACK_WEIGHT_KG = 1.000


def fetch_run(production_run_id):
    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM public.production_runs WHERE id = %s;",
                (production_run_id,),
            )
            return cursor.fetchone()


def checkpoint(label, expected, actual):
    ok = expected == actual
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")
    if not ok:
        raise AssertionError(f"CHECKPOINT FAILED: {label}")


def script_input(*answers):
    queue = list(answers)

    def fake_input(prompt=""):
        value = queue.pop(0)
        print(f"{prompt}{value}")
        return value

    builtins.input = fake_input


def new_test_run_row(customer, starting_pallets_remaining):
    return {
        "production_line": PRODUCTION_LINE,
        "line_technician": "TEST-TECHNICIAN",
        "shift": "TEST-SHIFT",
        "customer": customer,
        "product": "TEST-PRODUCT-DO-NOT-USE",
        "pack_weight_kg": TEST_PACK_WEIGHT_KG,
        "packs_per_case": 10,
        "pack_type": "TEST-PACK-TYPE",
        "target_speed_ppm": 100,
        "cases_per_pallet": 10,
        "starting_pallets_remaining": starting_pallets_remaining,
        "pallets_remaining": starting_pallets_remaining,
        "previous_run_completed": 0,
    }


def run():
    require_live_confirmation(
        "production_run_completion.py",
        "Creates and completes TEST production runs on the synthetic "
        "'TEST-LINE-COMPLETION' line, exercising the full completion "
        "lifecycle against Supabase.",
    )

    # The pack_weight reconstruction in recover_production_run() looks up
    # the recovered pack_weight_kg against pack_sizes_by_line[production_line].
    # TEST-LINE-COMPLETION is a synthetic, test-only line and has no entry
    # in that (production) configuration, so register one here - in this
    # process's memory only, for the lifetime of this run(). src/main.py's
    # real pack_sizes_by_line definition is never touched on disk.
    pulse_main.pack_sizes_by_line[PRODUCTION_LINE] = {
        TEST_PACK_SIZE_LABEL: TEST_PACK_WEIGHT_KG,
    }

    # ==========================================================
    # STAGE 1: TEST RUN STARTS ACTIVE
    # ==========================================================

    production_run_id = save_production_run(
        new_test_run_row("TEST-PHASE1-COMPLETION-1", 10)
    )
    print(f"Test production_run_id = {production_run_id}")

    active = get_active_production_run(PRODUCTION_LINE)
    checkpoint("get_active_production_run finds the TEST run", production_run_id, active["id"])
    checkpoint("Initial status is Active", "Active", active["status"])

    initial_row = fetch_run(production_run_id)
    checkpoint("Initial finished_at is NULL", None, initial_row["finished_at"])

    # ==========================================================
    # STAGE 2: PROGRESS AND PERSIST (real recovery + progress path)
    # ==========================================================

    run_state = pulse_main.recover_production_run(PRODUCTION_LINE)
    assert run_state is not None, "Recovery failed to find the newly created TEST run"

    checkpoint("Recovered pack_weight reconstructed correctly", TEST_PACK_SIZE_LABEL, run_state["pack_weight"])

    pulse_main.update_run_progress(
        run_state,
        {"pallets_completed_this_hour": 6},
    )

    save_hourly_update({
        "production_run_id": run_state["database_run_id"],
        "oee": 80.0,
        "pallets_completed": 6,
        "planned_downtime": "None",
        "expected_packs": 0,
        "actual_packs": 0,
        "expected_pallets": 0,
        "actual_pallets": 6,
        "production_variance_packs": 0,
        "estimated_lost_packs": 0,
        "estimated_lost_minutes": 0,
        "unexplained_loss": False,
        "unexplained_loss_reason": None,
        "pallets_remaining": run_state["pallets_remaining"],
    })

    hourly_progress_saved = pulse_main.persist_run_progress(run_state)
    checkpoint("Hourly progress snapshot saved", True, hourly_progress_saved)
    checkpoint("pallets_remaining after hour", 4, run_state["pallets_remaining"])
    checkpoint("total_pallets_completed after hour", 6, run_state["total_pallets_completed"])

    # ==========================================================
    # STAGE 3: REAL handle_run_completion()
    # ==========================================================

    script_input("Customer Changeover")

    pulse_main.handle_run_completion(run_state)

    checkpoint("changeover_type recorded", "Customer Changeover", run_state["changeover_type"])
    checkpoint("confirmed_overrun_pallets after changeover", 0, run_state["confirmed_overrun_pallets"])

    # ==========================================================
    # STAGE 4: FINAL CLOSURE GATE
    # (mirrors the exact sequence added to run_session())
    # ==========================================================

    final_progress_saved = pulse_main.persist_run_progress(run_state)
    checkpoint("Final progress persistence succeeded", True, final_progress_saved)

    closed_id = pulse_main.close_production_run(
        run_state["database_run_id"],
        pulse_main.current_timestamp(),
    )
    checkpoint("close_production_run returns the correct id", production_run_id, closed_id)

    # ==========================================================
    # STAGE 5/6: DATABASE ROW IS status=Completed, finished_at SET,
    # AND FINAL PROGRESS FIELDS ARE CORRECT
    # ==========================================================

    row = fetch_run(production_run_id)
    checkpoint("DB status is Completed", "Completed", row["status"])
    checkpoint("DB finished_at is set", True, row["finished_at"] is not None)
    checkpoint("DB finished_at >= started_at", True, row["finished_at"] >= row["started_at"])
    checkpoint("DB pallets_remaining preserved", 4, row["pallets_remaining"])
    checkpoint("DB total_pallets_completed preserved", 6, row["total_pallets_completed"])
    checkpoint("DB potential_overrun_pallets preserved", 0, row["potential_overrun_pallets"])
    checkpoint("DB confirmed_overrun_pallets preserved", 0, row["confirmed_overrun_pallets"])

    # ==========================================================
    # STAGE 8: get_active_production_run() NO LONGER RETURNS IT
    # ==========================================================

    checkpoint("No longer returned as active", None, get_active_production_run(PRODUCTION_LINE))

    # ==========================================================
    # STAGE 9: recover_production_run() RETURNS None
    # ==========================================================

    checkpoint("Recovery finds no active run", None, pulse_main.recover_production_run(PRODUCTION_LINE))

    # ==========================================================
    # STAGE 10: A SECOND RUN CAN NOW START ON THE SAME LINE
    # ==========================================================

    second_production_run_id = save_production_run(
        new_test_run_row("TEST-PHASE1-COMPLETION-2", 5)
    )
    print(f"Second test production_run_id = {second_production_run_id}")

    active_second = get_active_production_run(PRODUCTION_LINE)
    checkpoint("Second run is now the active run", second_production_run_id, active_second["id"])
    checkpoint("Second run status is Active", "Active", active_second["status"])

    # ==========================================================
    # STAGE 11: ORIGINAL COMPLETED RUN REMAINS IN HISTORY
    # ==========================================================

    original_row = fetch_run(production_run_id)
    checkpoint("Original run still exists", True, original_row is not None)
    checkpoint("Original run still shows Completed", "Completed", original_row["status"])

    # ==========================================================
    # SAFETY RULE: IF FINAL PROGRESS PERSISTENCE FAILS,
    # THE RUN MUST NOT BE MARKED COMPLETED
    # ==========================================================

    second_run = pulse_main.recover_production_run(PRODUCTION_LINE)
    real_database_run_id = second_run["database_run_id"]

    second_run["database_run_id"] = 999999999  # does not exist -> forces update_production_run_progress() to fail

    failed_persist = pulse_main.persist_run_progress(second_run)
    checkpoint("Simulated final persistence failure returns False", False, failed_persist)

    second_run["database_run_id"] = real_database_run_id  # restore

    # Mirroring run_session()'s gate: close_production_run() must never be
    # called when final_progress_saved is False. We do not call it here -
    # proving the second run's real row was never touched by this failure.
    second_row_after_failure = fetch_run(second_production_run_id)
    checkpoint("Second run status remains Active after failed persist", "Active", second_row_after_failure["status"])
    checkpoint("Second run finished_at still NULL after failed persist", None, second_row_after_failure["finished_at"])

    print()
    print("=== ALL CHECKPOINTS PASSED ===")
    print(f"first production_run_id (Completed) = {production_run_id}")
    print(f"second production_run_id (Active) = {second_production_run_id}")


if __name__ == "__main__":
    run()
