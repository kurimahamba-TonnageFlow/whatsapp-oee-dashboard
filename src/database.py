import os

import psycopg
from dotenv import load_dotenv


# ==========================================================
# ENVIRONMENT
# ==========================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


# ==========================================================
# DATABASE CONNECTION
# ==========================================================


def get_database_connection():
    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL was not found in .env"
        )

    return psycopg.connect(
        DATABASE_URL
    )


# ==========================================================
# PRODUCTION RUN
# ==========================================================


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
            cursor.execute(
                query,
                run,
            )

            saved_run = (
                cursor.fetchone()
            )

        connection.commit()

    if saved_run is None:
        raise RuntimeError(
            "Production Run was inserted "
            "but no database ID was returned."
        )

    return saved_run[0]


# ==========================================================
# HOURLY UPDATE
# ==========================================================


def save_hourly_update(update):
    query = """
        INSERT INTO public.hourly_updates (
            production_run_id,
            oee,
            pallets_completed,
            planned_downtime,
            expected_packs,
            actual_packs,
            expected_pallets,
            actual_pallets,
            production_variance_packs,
            estimated_lost_packs,
            estimated_lost_minutes,
            unexplained_loss,
            unexplained_loss_reason,
            pallets_remaining
        )
        VALUES (
            %(production_run_id)s,
            %(oee)s,
            %(pallets_completed)s,
            %(planned_downtime)s,
            %(expected_packs)s,
            %(actual_packs)s,
            %(expected_pallets)s,
            %(actual_pallets)s,
            %(production_variance_packs)s,
            %(estimated_lost_packs)s,
            %(estimated_lost_minutes)s,
            %(unexplained_loss)s,
            %(unexplained_loss_reason)s,
            %(pallets_remaining)s
        )
        RETURNING id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            saved_update = (
                cursor.fetchone()
            )

        connection.commit()

    if saved_update is None:
        raise RuntimeError(
            "Hourly Update was inserted "
            "but no database ID was returned."
        )

    return saved_update[0]