import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL was not found in .env")


test_run = {
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


insert_query = """
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


try:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                insert_query,
                test_run,
            )

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