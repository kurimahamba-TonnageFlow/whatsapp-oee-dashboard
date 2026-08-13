import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL was not found in .env")


try:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
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
                    previous_run_completed,
                    total_pallets_completed,
                    status,
                    started_at
                FROM public.production_runs
                WHERE production_line = %s
                  AND status = 'Active'
                ORDER BY started_at DESC
                LIMIT 1;
                """,
                ("Rovema",),
            )

            run = cursor.fetchone()

            if run is None:
                print("No active Rovema Production Run found.")

            else:
                print("\nActive Production Run recovered from Supabase.")
                print("--------------------------------------------")
                print(f"Run ID: {run[0]}")
                print(f"Line: {run[1]}")
                print(f"Technician: {run[2]}")
                print(f"Shift: {run[3]}")
                print(f"Customer: {run[4]}")
                print(f"Product: {run[5]}")
                print(f"Pack Weight: {run[6]} kg")
                print(f"Packs per Case: {run[7]}")
                print(f"Pack Type: {run[8]}")
                print(f"Target Speed: {run[9]} ppm")
                print(f"Cases per Pallet: {run[10]}")
                print(f"Starting Pallets Remaining: {run[11]}")
                print(f"Current Pallets Remaining: {run[12]}")
                print(f"Previous Run Completed: {run[13]}")
                print(f"Total Pallets Completed: {run[14]}")
                print(f"Status: {run[15]}")
                print(f"Started At: {run[16]}")

except Exception as error:
    print("Production Run recovery failed.")
    print(f"Error: {error}")