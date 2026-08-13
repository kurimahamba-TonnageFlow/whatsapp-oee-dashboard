import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_database_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL was not found in .env")

    return psycopg.connect(DATABASE_URL)

def save_production_run(run):
    query = """
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
        RETURNING id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, run)
            saved_run = cursor.fetchone()

    return saved_run[0]

    return psycopg.connect(DATABASE_URL)