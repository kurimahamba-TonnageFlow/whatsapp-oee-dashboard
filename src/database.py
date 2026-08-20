import os

import psycopg
from psycopg.rows import dict_row
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

def save_downtime_event(event):
    query = """
        INSERT INTO public.downtime_events (
            production_run_id,
            fault_id,
            machine,
            reason,
            reported_by,
            engineer_called,
            production_status,
            engineering_status,
            engineer,
            retrospective,
            opened_at,
            resolved_at
        )
        VALUES (
            %(production_run_id)s,
            %(fault_id)s,
            %(machine)s,
            %(reason)s,
            %(reported_by)s,
            %(engineer_called)s,
            %(production_status)s,
            %(engineering_status)s,
            %(engineer)s,
            %(retrospective)s,
            %(opened_at)s,
            %(resolved_at)s
        )
        RETURNING id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, event)
            downtime_event_id = cursor.fetchone()[0]

        connection.commit()

    return downtime_event_id

def save_engineering_update(update):
    query = """
        INSERT INTO public.engineering_updates (
            downtime_event_id,
            production_run_id,
            fault_id,
            engineer,
            update_type,
            finding,
            action,
            engineering_status
        )
        VALUES (
            %(downtime_event_id)s,
            %(production_run_id)s,
            %(fault_id)s,
            %(engineer)s,
            %(update_type)s,
            %(finding)s,
            %(action)s,
            %(engineering_status)s
        )
        RETURNING id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            saved_update = cursor.fetchone()

        connection.commit()

    if saved_update is None:
        raise RuntimeError(
            "Engineering Update was inserted "
            "but no database ID was returned."
        )

    return saved_update[0]


def get_open_faults(production_run_id):
    query = """
        SELECT *
        FROM public.downtime_events
        WHERE production_run_id = %s
        AND production_status = 'Ongoing'
        AND resolved_at IS NULL;
    """

    with get_database_connection() as connection:
       with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                (production_run_id,),
            )

            open_faults = cursor.fetchall()

    return open_faults

def get_active_production_run(production_line):
    query = """
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
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                (production_line,),
            )

            active_run = cursor.fetchone()

    return active_run

def update_downtime_event_state(
    downtime_event_id,
    engineer_called,
    production_status,
    engineering_status,
    engineer,
    resolved_at=None,
):
    query = """
        UPDATE public.downtime_events
        SET
            engineer_called = %(engineer_called)s,
            production_status = %(production_status)s,
            engineering_status = %(engineering_status)s,
            engineer = %(engineer)s,
            resolved_at = %(resolved_at)s
        WHERE id = %(downtime_event_id)s
        RETURNING id;
    """

    update = {
        "downtime_event_id":
            downtime_event_id,

        "engineer_called":
            engineer_called,

        "production_status":
            production_status,

        "engineering_status":
            engineering_status,

        "engineer":
            engineer,

        "resolved_at":
            resolved_at,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            updated_event = cursor.fetchone()

        connection.commit()

    if updated_event is None:
        raise RuntimeError(
            "Downtime Event was not updated."
        )

    return updated_event[0]
