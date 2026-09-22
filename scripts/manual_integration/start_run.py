"""
Manual live integration script (NOT a pytest test): inserts one
hardcoded TEST production run (line "Rovema", customer "Asda") directly
into the live Supabase database via a raw psycopg INSERT. Performs a
real write against the live database.

Never runs automatically - execute directly:
    python scripts/manual_integration/start_run.py
after setting the required confirmation environment variable (see
_safety.require_live_confirmation). Importing this module has no side
effects (including loading .env or reading DATABASE_URL, only ever
done inside run()); all execution lives inside run(), called only
from the __main__ guard below.
"""

import os
from pathlib import Path
import sys

import psycopg
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _safety import require_live_confirmation


TEST_RUN = {
    "production_line": "Rovema",
    "line_technician": "Liam",
    "shift": "Night",
    "customer": "Asda",
    "product": "Basmati",
    "pack_weight_kg": 1.000,
    "packs_per_case": 8,
    "pack_type": "Pillow",
    "target_speed_ppm": 120,
    "cases_per_pallet": 220,
    "starting_pallets_remaining": 38,
    "pallets_remaining": 38,
    "previous_run_completed": 38,
}


INSERT_QUERY = """
INSERT INTO public.production_runs (
    production_line,
    line_technician,
    shift,
    customer,
    product,
    pack_weight_kg,
    packs_per_case,
    pack_type,
    target_speed_ppm,
    cases_per_pallet,
    starting_pallets_remaining,
    pallets_remaining,
    previous_run_completed
)
VALUES (
    %(production_line)s,
    %(line_technician)s,
    %(shift)s,
    %(customer)s,
    %(product)s,
    %(pack_weight_kg)s,
    %(packs_per_case)s,
    %(pack_type)s,
    %(target_speed_ppm)s,
    %(cases_per_pallet)s,
    %(starting_pallets_remaining)s,
    %(pallets_remaining)s,
    %(previous_run_completed)s
)
RETURNING
    id,
    production_line,
    customer,
    product,
    status,
    started_at;
"""


def run():
    require_live_confirmation(
        "start_run.py",
        "Inserts one hardcoded TEST production run (line 'Rovema', "
        "customer 'Asda') directly into the live Supabase database.",
    )

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL was not found in .env")

    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(INSERT_QUERY, TEST_RUN)

                saved_run = cursor.fetchone()

                print("Production Run saved successfully.")
                print(f"Run ID: {saved_run[0]}")
                print(f"Line: {saved_run[1]}")
                print(f"Customer: {saved_run[2]}")
                print(f"Product: {saved_run[3]}")
                print(f"Status: {saved_run[4]}")
                print(f"Started At: {saved_run[5]}")

    except Exception as error:
        print("Production Run insert failed.")
        print(f"Error: {error}")


if __name__ == "__main__":
    run()
