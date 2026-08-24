"""
Proves production-run progress (pallets_remaining, total_pallets_completed,
potential_overrun_pallets, confirmed_overrun_pallets) survives an
application restart, using the real update_run_progress(), save_hourly_update(),
persist_run_progress() and recover_production_run() functions against Supabase.

Creates its own clearly-labelled TEST production run on a synthetic,
test-only production line ("TEST-LINE-PROGRESS") rather than hard-coding
any shared production_run_id or reusing a real factory line. A real line
can only ever hold one Active run at a time (idx_unique_active_run_per_line),
and there is intentionally no run-closing capability yet, so a synthetic
line keeps this test re-runnable without ever touching Rovema/GIC/Guill
data or a previous run of this same test.
"""

import builtins
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import main
from src.database import (
    save_production_run,
    save_hourly_update,
    get_database_connection,
)
from psycopg.rows import dict_row


PRODUCTION_LINE = "TEST-LINE-PROGRESS"


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


def apply_hour(run, pallets_completed, oee=80.0):
    """Mirrors the real run_session() hourly sequence: mutate in memory,
    write history, then write the current-state snapshot."""
    main.update_run_progress(
        run,
        {"pallets_completed_this_hour": pallets_completed},
    )

    save_hourly_update({
        "production_run_id": run["database_run_id"],
        "oee": oee,
        "pallets_completed": pallets_completed,
        "planned_downtime": "None",
        "expected_packs": 0,
        "actual_packs": 0,
        "expected_pallets": 0,
        "actual_pallets": pallets_completed,
        "production_variance_packs": 0,
        "estimated_lost_packs": 0,
        "estimated_lost_minutes": 0,
        "unexplained_loss": False,
        "unexplained_loss_reason": None,
        "pallets_remaining": run["pallets_remaining"],
    })

    saved = main.persist_run_progress(run)
    checkpoint("Progress snapshot write succeeded", True, saved)


# ==========================================================
# STAGE 1: CREATE A CLEARLY-LABELLED TEST PRODUCTION RUN
# ==========================================================

production_run_id = save_production_run({
    "production_line": PRODUCTION_LINE,
    "line_technician": "TEST-TECHNICIAN",
    "shift": "TEST-SHIFT",
    "customer": "TEST-PHASE1-PROGRESS",
    "product": "TEST-PRODUCT-DO-NOT-USE",
    "pack_weight_kg": 1.000,
    "packs_per_case": 10,
    "pack_type": "TEST-PACK-TYPE",
    "target_speed_ppm": 100,
    "cases_per_pallet": 10,
    "starting_pallets_remaining": 38,
    "pallets_remaining": 38,
    "previous_run_completed": 0,
})

print(f"Test production_run_id = {production_run_id}")

run = main.recover_production_run(PRODUCTION_LINE)
assert run is not None, "Recovery failed to find the newly created TEST run"

checkpoint("Recovered run is the TEST run just created", production_run_id, run["database_run_id"])
checkpoint("Initial pallets_remaining", 38, run["pallets_remaining"])
checkpoint("Initial total_pallets_completed", 0, run["total_pallets_completed"])
checkpoint("Initial potential_overrun_pallets", 0, run["potential_overrun_pallets"])
checkpoint("Initial confirmed_overrun_pallets", 0, run["confirmed_overrun_pallets"])


# ==========================================================
# STAGE 2: HOUR 1 (+4) -> 34 remaining, 4 completed
# ==========================================================

apply_hour(run, 4)
checkpoint("Hour 1 (memory): pallets_remaining", 34, run["pallets_remaining"])
checkpoint("Hour 1 (memory): total_pallets_completed", 4, run["total_pallets_completed"])

row = fetch_run(production_run_id)
checkpoint("Hour 1 (DB): pallets_remaining", 34, row["pallets_remaining"])
checkpoint("Hour 1 (DB): total_pallets_completed", 4, row["total_pallets_completed"])


# ==========================================================
# STAGE 3: HOUR 2 (+5) -> 29 remaining, 9 completed
# ==========================================================

apply_hour(run, 5)
checkpoint("Hour 2 (memory): pallets_remaining", 29, run["pallets_remaining"])
checkpoint("Hour 2 (memory): total_pallets_completed", 9, run["total_pallets_completed"])

row = fetch_run(production_run_id)
checkpoint("Hour 2 (DB): pallets_remaining", 29, row["pallets_remaining"])
checkpoint("Hour 2 (DB): total_pallets_completed", 9, row["total_pallets_completed"])


# ==========================================================
# STAGE 4: SIMULATE APPLICATION RESTART (fresh recovery call,
# no reuse of the in-memory `run` dict above)
# ==========================================================

recovered = main.recover_production_run(PRODUCTION_LINE)
checkpoint("Restart recovery: pallets_remaining", 29, recovered["pallets_remaining"])
checkpoint("Restart recovery: total_pallets_completed", 9, recovered["total_pallets_completed"])
checkpoint("Recovered dict has pallets_remaining key", True, "pallets_remaining" in recovered)
checkpoint("Recovered dict has total_pallets_completed key", True, "total_pallets_completed" in recovered)
checkpoint("Recovered dict has potential_overrun_pallets key", True, "potential_overrun_pallets" in recovered)
checkpoint("Recovered dict has confirmed_overrun_pallets key", True, "confirmed_overrun_pallets" in recovered)


# ==========================================================
# STAGE 5: TWO CONSECUTIVE RECOVERIES WITHOUT AN UPDATE
# MUST RETURN IDENTICAL PROGRESS
# ==========================================================

recovered_again = main.recover_production_run(PRODUCTION_LINE)
checkpoint("Repeat recovery: pallets_remaining unchanged", recovered["pallets_remaining"], recovered_again["pallets_remaining"])
checkpoint("Repeat recovery: total_pallets_completed unchanged", recovered["total_pallets_completed"], recovered_again["total_pallets_completed"])
checkpoint("Repeat recovery: potential_overrun_pallets unchanged", recovered["potential_overrun_pallets"], recovered_again["potential_overrun_pallets"])
checkpoint("Repeat recovery: confirmed_overrun_pallets unchanged", recovered["confirmed_overrun_pallets"], recovered_again["confirmed_overrun_pallets"])


# ==========================================================
# STAGE 6: CONTINUE THE LIFECYCLE ON THE RECOVERED RUN
# HOUR 3 (+3) -> 26 remaining, 12 completed
# Proves the restart did NOT double-count the previous 9 pallets:
# a stale recovery (remaining=38) would produce 35/7 instead.
# ==========================================================

apply_hour(recovered, 3)
checkpoint("Hour 3 (memory): pallets_remaining", 26, recovered["pallets_remaining"])
checkpoint("Hour 3 (memory): total_pallets_completed", 12, recovered["total_pallets_completed"])

row = fetch_run(production_run_id)
checkpoint("Hour 3 (DB): pallets_remaining", 26, row["pallets_remaining"])
checkpoint("Hour 3 (DB): total_pallets_completed", 12, row["total_pallets_completed"])


# ==========================================================
# STAGE 7: RECOVER AGAIN -> STILL 26 / 12
# ==========================================================

final_recovery = main.recover_production_run(PRODUCTION_LINE)
checkpoint("Final recovery: pallets_remaining", 26, final_recovery["pallets_remaining"])
checkpoint("Final recovery: total_pallets_completed", 12, final_recovery["total_pallets_completed"])


# ==========================================================
# STAGE 8: POTENTIAL_OVERRUN_PALLETS SURVIVES RECOVERY
# Complete more than remains (26) to force an overrun.
# ==========================================================

apply_hour(final_recovery, 30)
checkpoint("Overrun hour (memory): pallets_remaining", 0, final_recovery["pallets_remaining"])
checkpoint("Overrun hour (memory): total_pallets_completed", 38, final_recovery["total_pallets_completed"])
checkpoint("Overrun hour (memory): potential_overrun_pallets", 4, final_recovery["potential_overrun_pallets"])

overrun_recovery = main.recover_production_run(PRODUCTION_LINE)
checkpoint("potential_overrun_pallets survives recovery", 4, overrun_recovery["potential_overrun_pallets"])
checkpoint("confirmed_overrun_pallets still 0 before changeover", 0, overrun_recovery["confirmed_overrun_pallets"])


# ==========================================================
# STAGE 9: CONFIRMED_OVERRUN_PALLETS SURVIVES RECOVERY
# Exercise the real handle_run_completion() (Product Changeover
# branch), scripting its single prompt.
# ==========================================================

_answers = ["Product Changeover"]


def _fake_input(prompt=""):
    value = _answers.pop(0)
    print(f"{prompt}{value}")
    return value


builtins.input = _fake_input

main.handle_run_completion(overrun_recovery)

checkpoint("Changeover (memory): confirmed_overrun_pallets", 4, overrun_recovery["confirmed_overrun_pallets"])

row = fetch_run(production_run_id)
checkpoint("Changeover (DB): confirmed_overrun_pallets", 4, row["confirmed_overrun_pallets"])

post_changeover_recovery = main.recover_production_run(PRODUCTION_LINE)
checkpoint("confirmed_overrun_pallets survives recovery", 4, post_changeover_recovery["confirmed_overrun_pallets"])


print()
print("=== ALL CHECKPOINTS PASSED ===")
print(f"production_run_id = {production_run_id}")
