import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
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
            planned_downtime_minutes,
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
            %(planned_downtime_minutes)s,
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
            potential_overrun_pallets,
            confirmed_overrun_pallets,
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

def update_production_run_progress(
    production_run_id,
    pallets_remaining,
    total_pallets_completed,
    potential_overrun_pallets,
    confirmed_overrun_pallets,
):
    query = """
        UPDATE public.production_runs
        SET
            pallets_remaining = %(pallets_remaining)s,
            total_pallets_completed = %(total_pallets_completed)s,
            potential_overrun_pallets = %(potential_overrun_pallets)s,
            confirmed_overrun_pallets = %(confirmed_overrun_pallets)s
        WHERE id = %(production_run_id)s
        RETURNING id;
    """

    update = {
        "production_run_id":
            production_run_id,

        "pallets_remaining":
            pallets_remaining,

        "total_pallets_completed":
            total_pallets_completed,

        "potential_overrun_pallets":
            potential_overrun_pallets,

        "confirmed_overrun_pallets":
            confirmed_overrun_pallets,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            updated_run = cursor.fetchone()

        connection.commit()

    if updated_run is None:
        raise RuntimeError(
            "Production Run progress was not updated."
        )

    return updated_run[0]

def save_changeover_type(
    production_run_id,
    changeover_type,
):
    query = """
        UPDATE public.production_runs
        SET
            changeover_type = %(changeover_type)s
        WHERE id = %(production_run_id)s
        RETURNING id;
    """

    update = {
        "production_run_id":
            production_run_id,

        "changeover_type":
            changeover_type,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            updated_run = cursor.fetchone()

        connection.commit()

    if updated_run is None:
        raise RuntimeError(
            "Production Run changeover type was not saved."
        )

    return updated_run[0]


def get_production_run_by_id(production_run_id):
    """Plain, unfiltered lookup by id - unlike the dashboard read
    functions, this does NOT exclude TEST- rows, since operational
    endpoints (e.g. completing a run) must see every real row
    regardless of naming convention."""
    query = """
        SELECT
            id,
            production_line,
            status
        FROM public.production_runs
        WHERE id = %(production_run_id)s
        LIMIT 1;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"production_run_id": production_run_id})
            return cursor.fetchone()


def close_production_run(
    production_run_id,
    finished_at,
):
    query = """
        UPDATE public.production_runs
        SET
            status = 'Completed',
            finished_at = %(finished_at)s
        WHERE id = %(production_run_id)s
        RETURNING id;
    """

    update = {
        "production_run_id":
            production_run_id,

        "finished_at":
            finished_at,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                update,
            )

            closed_run = cursor.fetchone()

        connection.commit()

    if closed_run is None:
        raise RuntimeError(
            "Production Run was not closed."
        )

    return closed_run[0]

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


# ==========================================================
# DASHBOARD READ API
# ==========================================================
#
# Read-only. Every query below applies _TEST_DATA_EXCLUSION_SQL so
# test/demo data (see tests/test_phase1_mvp_system.py and friends)
# never appears in dashboard results without deleting anything.
#
# All filter values are bound as parameters (%(name)s) - never string-
# interpolated into SQL. _TEST_DATA_EXCLUSION_SQL itself is a fixed
# literal maintained by this codebase, not user input.
#
# Schema gaps affecting these queries (see docs/dashboard_integration.md):
#   - hourly_updates has no timestamp column, so per-hour ordering uses
#     submission sequence (row id), not wall-clock time.
#   - engineering_updates has no timestamp column either; date filters
#     for it are approximated via its parent downtime_events.opened_at.
#   - There is no fault/downtime-type taxonomy beyond free text, so
#     "Machine Setup" vs "Machine Repair" cannot be computed here.

_TEST_DATA_EXCLUSION_SQL = """
    pr.production_line NOT ILIKE 'TEST-%'
    AND pr.customer NOT ILIKE '%TEST-%'
    AND pr.product NOT ILIKE '%TEST-%'
    AND pr.shift NOT ILIKE '%TEST-%'
"""


def _run_conditions(filters):
    """Conditions/params for queries filtered at the production_runs
    level (aliased pr). Applies: date_from/date_to (pr.started_at date),
    production_line, shift, product, customer, technician, run_status."""
    filters = filters or {}
    conditions = [_TEST_DATA_EXCLUSION_SQL]
    params = {}

    if filters.get("date_from") is not None:
        conditions.append("pr.started_at::date >= %(date_from)s")
        params["date_from"] = filters["date_from"]

    if filters.get("date_to") is not None:
        conditions.append("pr.started_at::date <= %(date_to)s")
        params["date_to"] = filters["date_to"]

    if filters.get("production_line") is not None:
        conditions.append("pr.production_line = %(production_line)s")
        params["production_line"] = filters["production_line"]

    if filters.get("shift") is not None:
        conditions.append("pr.shift = %(shift)s")
        params["shift"] = filters["shift"]

    if filters.get("product") is not None:
        conditions.append("pr.product = %(product)s")
        params["product"] = filters["product"]

    if filters.get("customer") is not None:
        conditions.append("pr.customer = %(customer)s")
        params["customer"] = filters["customer"]

    if filters.get("technician") is not None:
        conditions.append("pr.line_technician = %(technician)s")
        params["technician"] = filters["technician"]

    if filters.get("run_status") is not None:
        conditions.append("pr.status = %(run_status)s")
        params["run_status"] = filters["run_status"]

    return conditions, params


def _hourly_conditions(filters):
    """_run_conditions plus hourly_updates.planned_downtime (downtime_type).
    Used for queries joining hourly_updates AS hu to production_runs AS pr."""
    conditions, params = _run_conditions(filters)
    filters = filters or {}

    if filters.get("downtime_type") is not None:
        conditions.append("hu.planned_downtime = %(downtime_type)s")
        params["downtime_type"] = filters["downtime_type"]

    return conditions, params


def _fault_conditions(filters):
    """_run_conditions (date range reinterpreted against downtime_events.
    opened_at, since a fault may open on a different date than its run
    started) plus machine (partial match), engineer, fault_status.
    Used for queries joining downtime_events AS de to production_runs AS pr."""
    filters = filters or {}
    conditions = [_TEST_DATA_EXCLUSION_SQL]
    params = {}

    if filters.get("date_from") is not None:
        conditions.append("de.opened_at::date >= %(date_from)s")
        params["date_from"] = filters["date_from"]

    if filters.get("date_to") is not None:
        conditions.append("de.opened_at::date <= %(date_to)s")
        params["date_to"] = filters["date_to"]

    if filters.get("production_line") is not None:
        conditions.append("pr.production_line = %(production_line)s")
        params["production_line"] = filters["production_line"]

    if filters.get("shift") is not None:
        conditions.append("pr.shift = %(shift)s")
        params["shift"] = filters["shift"]

    if filters.get("product") is not None:
        conditions.append("pr.product = %(product)s")
        params["product"] = filters["product"]

    if filters.get("customer") is not None:
        conditions.append("pr.customer = %(customer)s")
        params["customer"] = filters["customer"]

    if filters.get("technician") is not None:
        conditions.append("pr.line_technician = %(technician)s")
        params["technician"] = filters["technician"]

    if filters.get("run_status") is not None:
        conditions.append("pr.status = %(run_status)s")
        params["run_status"] = filters["run_status"]

    if filters.get("machine") is not None:
        conditions.append("de.machine ILIKE %(machine)s")
        params["machine"] = f"%{filters['machine']}%"

    if filters.get("engineer") is not None:
        conditions.append("de.engineer = %(engineer)s")
        params["engineer"] = filters["engineer"]

    if filters.get("fault_status") is not None:
        conditions.append("de.production_status = %(fault_status)s")
        params["fault_status"] = filters["fault_status"]

    return conditions, params


def _engineering_conditions(filters):
    """Same base as _fault_conditions (joined via downtime_events AS de,
    since engineering_updates has no timestamp/production_line of its
    own) plus engineer and engineering_class (update_type)."""
    conditions, params = _fault_conditions(filters)
    filters = filters or {}

    if filters.get("engineering_class") is not None:
        conditions.append("eu.update_type = %(engineering_class)s")
        params["engineering_class"] = filters["engineering_class"]

    return conditions, params


def get_dashboard_filter_options():
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            def distinct_run_values(column):
                cursor.execute(
                    f"""
                    SELECT DISTINCT {column}
                    FROM public.production_runs AS pr
                    WHERE {_TEST_DATA_EXCLUSION_SQL}
                    ORDER BY {column};
                    """
                )
                return [row[0] for row in cursor.fetchall() if row[0] is not None]

            production_lines = distinct_run_values("production_line")
            shifts = distinct_run_values("shift")
            products = distinct_run_values("product")
            customers = distinct_run_values("customer")
            technicians = distinct_run_values("line_technician")
            run_statuses = distinct_run_values("status")

            cursor.execute(
                f"""
                SELECT DISTINCT de.machine
                FROM public.downtime_events AS de
                JOIN public.production_runs AS pr ON pr.id = de.production_run_id
                WHERE {_TEST_DATA_EXCLUSION_SQL}
                ORDER BY de.machine;
                """
            )
            machines = [row[0] for row in cursor.fetchall() if row[0] is not None]

            cursor.execute(
                f"""
                SELECT DISTINCT de.production_status
                FROM public.downtime_events AS de
                JOIN public.production_runs AS pr ON pr.id = de.production_run_id
                WHERE {_TEST_DATA_EXCLUSION_SQL}
                ORDER BY de.production_status;
                """
            )
            fault_statuses = [row[0] for row in cursor.fetchall() if row[0] is not None]

            cursor.execute(
                f"""
                SELECT DISTINCT eu.engineer
                FROM public.engineering_updates AS eu
                JOIN public.downtime_events AS de ON de.id = eu.downtime_event_id
                JOIN public.production_runs AS pr ON pr.id = eu.production_run_id
                WHERE {_TEST_DATA_EXCLUSION_SQL}
                ORDER BY eu.engineer;
                """
            )
            engineers = [row[0] for row in cursor.fetchall() if row[0] is not None]

            cursor.execute(
                f"""
                SELECT DISTINCT eu.update_type
                FROM public.engineering_updates AS eu
                JOIN public.downtime_events AS de ON de.id = eu.downtime_event_id
                JOIN public.production_runs AS pr ON pr.id = eu.production_run_id
                WHERE {_TEST_DATA_EXCLUSION_SQL}
                ORDER BY eu.update_type;
                """
            )
            engineering_classes = [row[0] for row in cursor.fetchall() if row[0] is not None]

            cursor.execute(
                f"""
                SELECT DISTINCT hu.planned_downtime
                FROM public.hourly_updates AS hu
                JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
                WHERE {_TEST_DATA_EXCLUSION_SQL}
                ORDER BY hu.planned_downtime;
                """
            )
            downtime_types = [row[0] for row in cursor.fetchall() if row[0] is not None]

    return {
        "production_lines": production_lines,
        "shifts": shifts,
        "products": products,
        "customers": customers,
        "technicians": technicians,
        "engineers": engineers,
        "machines": machines,
        "downtime_types": downtime_types,
        "engineering_classes": engineering_classes,
        "run_statuses": run_statuses,
        "fault_statuses": fault_statuses,
        # "format" has no reliable column mapping anywhere in the schema
        # (see docs/dashboard_integration.md) - documented, not guessed.
        "unsupported_filters": ["format"],
    }


def list_dashboard_runs(filters=None, limit=25, offset=0):
    conditions, params = _run_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            id AS run_id,
            production_line,
            line_technician,
            shift,
            customer,
            product,
            pack_type,
            status,
            started_at,
            finished_at,
            pallets_remaining,
            total_pallets_completed,
            changeover_type
        FROM public.production_runs AS pr
        WHERE {where_sql}
        ORDER BY started_at DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    count_query = f"""
        SELECT COUNT(*)
        FROM public.production_runs AS pr
        WHERE {where_sql};
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {**params, "limit": limit, "offset": offset})
            rows = cursor.fetchall()

        with connection.cursor() as count_cursor:
            count_cursor.execute(count_query, params)
            total = count_cursor.fetchone()[0]

    return rows, total


def get_dashboard_run(run_id):
    query = f"""
        SELECT
            id AS run_id,
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
            potential_overrun_pallets,
            confirmed_overrun_pallets,
            status,
            started_at,
            finished_at,
            changeover_type
        FROM public.production_runs AS pr
        WHERE pr.id = %(run_id)s
          AND {_TEST_DATA_EXCLUSION_SQL}
        LIMIT 1;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"run_id": run_id})
            run = cursor.fetchone()

    return run


def get_dashboard_hourly_updates(filters=None):
    conditions, params = _hourly_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            hu.id,
            hu.production_run_id,
            pr.production_line,
            hu.oee,
            hu.pallets_completed,
            hu.planned_downtime,
            hu.planned_downtime_minutes,
            hu.expected_packs,
            hu.actual_packs,
            hu.expected_pallets,
            hu.actual_pallets,
            hu.production_variance_packs,
            hu.estimated_lost_packs,
            hu.estimated_lost_minutes,
            hu.unexplained_loss,
            hu.unexplained_loss_reason,
            hu.pallets_remaining
        FROM public.hourly_updates AS hu
        JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
        WHERE {where_sql}
        ORDER BY hu.production_run_id, hu.id;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_output_timeline(filters=None):
    conditions, params = _hourly_conditions(filters)
    where_sql = " AND ".join(conditions)

    # No timestamp column exists on hourly_updates - sequence_in_run
    # (submission order via id) is the only available ordering proxy.
    query = f"""
        SELECT
            hu.id AS hourly_update_id,
            hu.production_run_id,
            pr.production_line,
            pr.pack_weight_kg,
            pr.packs_per_case,
            pr.cases_per_pallet,
            hu.expected_pallets,
            hu.actual_pallets,
            ROW_NUMBER() OVER (
                PARTITION BY hu.production_run_id
                ORDER BY hu.id
            ) AS sequence_in_run
        FROM public.hourly_updates AS hu
        JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
        WHERE {where_sql}
        ORDER BY hu.production_run_id, hu.id;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_planned_downtime(filters=None):
    conditions, params = _hourly_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            hu.planned_downtime AS downtime_type,
            COALESCE(SUM(hu.planned_downtime_minutes), 0) AS total_minutes,
            COUNT(*) AS occurrences
        FROM public.hourly_updates AS hu
        JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
        WHERE {where_sql}
        GROUP BY hu.planned_downtime
        ORDER BY total_minutes DESC;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_downtime_events(filters=None):
    """Raw downtime_events rows (no computed duration). Building block
    for /engineering-downtime; see get_dashboard_faults for the
    duration-enriched version used by /faults."""
    conditions, params = _fault_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            de.id AS downtime_event_id,
            de.production_run_id,
            pr.production_line,
            de.fault_id,
            de.machine,
            de.reason,
            de.reported_by,
            de.engineer_called,
            de.production_status,
            de.engineering_status,
            de.engineer,
            de.retrospective,
            de.opened_at,
            de.resolved_at
        FROM public.downtime_events AS de
        JOIN public.production_runs AS pr ON pr.id = de.production_run_id
        WHERE {where_sql}
        ORDER BY de.opened_at DESC;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_engineering_updates(filters=None):
    conditions, params = _engineering_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            eu.id,
            eu.downtime_event_id,
            eu.production_run_id,
            pr.production_line,
            eu.fault_id,
            eu.engineer,
            eu.update_type,
            eu.finding,
            eu.action,
            eu.engineering_status,
            de.machine,
            de.opened_at,
            de.resolved_at
        FROM public.engineering_updates AS eu
        JOIN public.downtime_events AS de ON de.id = eu.downtime_event_id
        JOIN public.production_runs AS pr ON pr.id = eu.production_run_id
        WHERE {where_sql}
        ORDER BY eu.id DESC;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_faults(filters=None):
    """downtime_events enriched with a computed duration, for /faults.
    duration_minutes uses resolved_at when present, else NOW() (server
    UTC time) - duration_is_active marks that second case."""
    conditions, params = _fault_conditions(filters)
    where_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            de.id AS downtime_event_id,
            de.production_run_id,
            pr.production_line,
            de.fault_id,
            de.machine,
            de.reason,
            de.reported_by,
            de.engineer_called,
            de.production_status,
            de.engineering_status,
            de.engineer,
            de.retrospective,
            de.opened_at,
            de.resolved_at,
            EXTRACT(
                EPOCH FROM (COALESCE(de.resolved_at, NOW()) - de.opened_at)
            ) / 60.0 AS duration_minutes,
            (de.resolved_at IS NULL) AS duration_is_active
        FROM public.downtime_events AS de
        JOIN public.production_runs AS pr ON pr.id = de.production_run_id
        WHERE {where_sql}
        ORDER BY de.opened_at DESC;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return rows


def get_dashboard_summary(filters=None):
    run_conditions, run_params = _run_conditions(filters)
    run_where = " AND ".join(run_conditions)

    hourly_conditions, hourly_params = _hourly_conditions(filters)
    hourly_where = " AND ".join(hourly_conditions)

    fault_conditions, fault_params = _fault_conditions(filters)
    fault_where = " AND ".join(fault_conditions)

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total_runs
                FROM public.production_runs AS pr
                WHERE {run_where};
                """,
                run_params,
            )
            total_runs = cursor.fetchone()["total_runs"]

            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(hu.expected_pallets), 0) AS expected_pallets,
                    COALESCE(SUM(hu.actual_pallets), 0) AS actual_pallets,
                    COALESCE(
                        SUM(
                            hu.expected_pallets
                            * pr.cases_per_pallet
                            * pr.packs_per_case
                            * pr.pack_weight_kg
                        ) / 1000.0,
                        0
                    ) AS expected_tonnes,
                    COALESCE(
                        SUM(
                            hu.actual_pallets
                            * pr.cases_per_pallet
                            * pr.packs_per_case
                            * pr.pack_weight_kg
                        ) / 1000.0,
                        0
                    ) AS actual_tonnes,
                    COALESCE(SUM(hu.planned_downtime_minutes), 0) AS planned_downtime_minutes,
                    COALESCE(SUM(hu.estimated_lost_packs), 0) AS estimated_lost_packs,
                    COALESCE(SUM(hu.estimated_lost_minutes), 0) AS estimated_lost_minutes,
                    COALESCE(
                        SUM(
                            hu.estimated_lost_packs
                            / NULLIF(pr.packs_per_case, 0)
                            / NULLIF(pr.cases_per_pallet, 0)
                        ),
                        0
                    ) AS estimated_lost_pallets,
                    COALESCE(
                        SUM(hu.estimated_lost_packs * pr.pack_weight_kg) / 1000.0,
                        0
                    ) AS estimated_lost_tonnes
                FROM public.hourly_updates AS hu
                JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
                WHERE {hourly_where};
                """,
                hourly_params,
            )
            hourly_totals = cursor.fetchone()

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE de.production_status = 'Ongoing') AS open_faults,
                    COUNT(*) FILTER (WHERE de.production_status = 'Resolved') AS resolved_faults,
                    COALESCE(
                        SUM(
                            EXTRACT(
                                EPOCH FROM (COALESCE(de.resolved_at, NOW()) - de.opened_at)
                            ) / 60.0
                        ),
                        0
                    ) AS unplanned_downtime_minutes,
                    COALESCE(BOOL_OR(de.resolved_at IS NULL), FALSE) AS includes_active_faults
                FROM public.downtime_events AS de
                JOIN public.production_runs AS pr ON pr.id = de.production_run_id
                WHERE {fault_where};
                """,
                fault_params,
            )
            fault_totals = cursor.fetchone()

    expected_pallets = float(hourly_totals["expected_pallets"])
    actual_pallets = float(hourly_totals["actual_pallets"])
    expected_tonnes = float(hourly_totals["expected_tonnes"])
    actual_tonnes = float(hourly_totals["actual_tonnes"])

    return {
        "total_runs": total_runs,
        "expected_pallets": expected_pallets,
        "actual_pallets": actual_pallets,
        "expected_tonnes": expected_tonnes,
        "actual_tonnes": actual_tonnes,
        "output_gap_pallets": max(expected_pallets - actual_pallets, 0),
        "output_gap_tonnes": max(expected_tonnes - actual_tonnes, 0),
        "target_achievement_percent": (
            (actual_pallets / expected_pallets * 100)
            if expected_pallets > 0
            else None
        ),
        "planned_downtime_minutes": float(hourly_totals["planned_downtime_minutes"]),
        "unplanned_downtime_minutes": float(fault_totals["unplanned_downtime_minutes"]),
        "unplanned_downtime_includes_active_faults": bool(
            fault_totals["includes_active_faults"]
        ),
        "estimated_lost_packs": float(hourly_totals["estimated_lost_packs"]),
        "estimated_lost_minutes": float(hourly_totals["estimated_lost_minutes"]),
        "estimated_lost_pallets": float(hourly_totals["estimated_lost_pallets"]),
        "estimated_lost_tonnes": float(hourly_totals["estimated_lost_tonnes"]),
        "open_faults": fault_totals["open_faults"],
        "resolved_faults": fault_totals["resolved_faults"],
        "machine_setup_minutes": None,
        "machine_repair_minutes": None,
        "machine_classification_status": "not_captured",
    }


# ==========================================================
# MANAGEMENT AREA
# ==========================================================
#
# Config tables (production_lines, machines, buttons) and the audit
# log are new, additive tables (see migrations/0001_management_area.sql).
# Disable/rename operations are always UPDATE, never DELETE, so
# historical downtime_events/engineering_updates rows (which reference
# machines only by free-text `machine` name, not a foreign key) stay
# valid regardless of later renames.
#
# Deliberately NOT applying _TEST_DATA_EXCLUSION_SQL here: Management
# must be able to see and force-close TEST-marked runs too (this is
# exactly the manual process used earlier to clear stuck test runs).


# ----------------------------------------------------------
# PRODUCTION LINES
# ----------------------------------------------------------


def list_production_lines():
    query = """
        SELECT id, name, active, display_order, created_at, updated_at
        FROM public.production_lines
        ORDER BY display_order, name;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return cursor.fetchall()


def get_production_line(line_id):
    query = """
        SELECT id, name, active, display_order, created_at, updated_at
        FROM public.production_lines
        WHERE id = %(line_id)s
        LIMIT 1;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"line_id": line_id})
            return cursor.fetchone()


def create_production_line(name, display_order=0):
    query = """
        INSERT INTO public.production_lines (name, display_order)
        VALUES (%(name)s, %(display_order)s)
        RETURNING id, name, active, display_order, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"name": name, "display_order": display_order})
            created = cursor.fetchone()

        connection.commit()

    return created


def update_production_line(line_id, name=None, active=None, display_order=None):
    fields = []
    params = {"line_id": line_id}

    if name is not None:
        fields.append("name = %(name)s")
        params["name"] = name

    if active is not None:
        fields.append("active = %(active)s")
        params["active"] = active

    if display_order is not None:
        fields.append("display_order = %(display_order)s")
        params["display_order"] = display_order

    fields.append("updated_at = now()")

    query = f"""
        UPDATE public.production_lines
        SET {", ".join(fields)}
        WHERE id = %(line_id)s
        RETURNING id, name, active, display_order, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            updated = cursor.fetchone()

        connection.commit()

    return updated


# ----------------------------------------------------------
# MACHINES / SECTIONS
# ----------------------------------------------------------


def list_machines(line_id):
    query = """
        SELECT id, production_line_id, name, active, display_order, created_at, updated_at
        FROM public.machines
        WHERE production_line_id = %(line_id)s
        ORDER BY display_order, name;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"line_id": line_id})
            return cursor.fetchall()


def get_machine(machine_id):
    query = """
        SELECT id, production_line_id, name, active, display_order, created_at, updated_at
        FROM public.machines
        WHERE id = %(machine_id)s
        LIMIT 1;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"machine_id": machine_id})
            return cursor.fetchone()


def create_machine(line_id, name, display_order=0):
    query = """
        INSERT INTO public.machines (production_line_id, name, display_order)
        VALUES (%(line_id)s, %(name)s, %(display_order)s)
        RETURNING id, production_line_id, name, active, display_order, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                {"line_id": line_id, "name": name, "display_order": display_order},
            )
            created = cursor.fetchone()

        connection.commit()

    return created


def update_machine(machine_id, name=None, active=None, display_order=None):
    fields = []
    params = {"machine_id": machine_id}

    if name is not None:
        fields.append("name = %(name)s")
        params["name"] = name

    if active is not None:
        fields.append("active = %(active)s")
        params["active"] = active

    if display_order is not None:
        fields.append("display_order = %(display_order)s")
        params["display_order"] = display_order

    fields.append("updated_at = now()")

    query = f"""
        UPDATE public.machines
        SET {", ".join(fields)}
        WHERE id = %(machine_id)s
        RETURNING id, production_line_id, name, active, display_order, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            updated = cursor.fetchone()

        connection.commit()

    return updated


# ----------------------------------------------------------
# FAULT / PLANNED-DOWNTIME BUTTONS
# ----------------------------------------------------------


def list_buttons(machine_id):
    query = """
        SELECT
            id, machine_id, name, event_type, ownership, fault_category,
            display_order, active, created_at, updated_at
        FROM public.buttons
        WHERE machine_id = %(machine_id)s
        ORDER BY display_order, name;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"machine_id": machine_id})
            return cursor.fetchall()


def get_button(button_id):
    query = """
        SELECT
            id, machine_id, name, event_type, ownership, fault_category,
            display_order, active, created_at, updated_at
        FROM public.buttons
        WHERE id = %(button_id)s
        LIMIT 1;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, {"button_id": button_id})
            return cursor.fetchone()


def create_button(
    machine_id,
    name,
    event_type,
    ownership,
    fault_category=None,
    display_order=0,
):
    query = """
        INSERT INTO public.buttons (
            machine_id, name, event_type, ownership, fault_category, display_order
        )
        VALUES (
            %(machine_id)s, %(name)s, %(event_type)s, %(ownership)s,
            %(fault_category)s, %(display_order)s
        )
        RETURNING
            id, machine_id, name, event_type, ownership, fault_category,
            display_order, active, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                {
                    "machine_id": machine_id,
                    "name": name,
                    "event_type": event_type,
                    "ownership": ownership,
                    "fault_category": fault_category,
                    "display_order": display_order,
                },
            )
            created = cursor.fetchone()

        connection.commit()

    return created


def update_button(
    button_id,
    name=None,
    event_type=None,
    ownership=None,
    fault_category=None,
    display_order=None,
    active=None,
):
    # Note: passing None for fault_category means "leave unchanged", not
    # "clear it" - there is no way to blank an existing fault_category via
    # this dynamic-update pattern (matches how every other optional field
    # here behaves). Not needed for the MVP; documented as a limitation.
    fields = []
    params = {"button_id": button_id}

    if name is not None:
        fields.append("name = %(name)s")
        params["name"] = name

    if event_type is not None:
        fields.append("event_type = %(event_type)s")
        params["event_type"] = event_type

    if ownership is not None:
        fields.append("ownership = %(ownership)s")
        params["ownership"] = ownership

    if fault_category is not None:
        fields.append("fault_category = %(fault_category)s")
        params["fault_category"] = fault_category

    if display_order is not None:
        fields.append("display_order = %(display_order)s")
        params["display_order"] = display_order

    if active is not None:
        fields.append("active = %(active)s")
        params["active"] = active

    fields.append("updated_at = now()")

    query = f"""
        UPDATE public.buttons
        SET {", ".join(fields)}
        WHERE id = %(button_id)s
        RETURNING
            id, machine_id, name, event_type, ownership, fault_category,
            display_order, active, created_at, updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            updated = cursor.fetchone()

        connection.commit()

    return updated


# ----------------------------------------------------------
# PUBLIC HMI CONFIGURATION (read-only, active rows only)
# ----------------------------------------------------------


def get_public_hmi_config():
    """Flat rows of every active line -> active machine -> active button.
    The API layer assembles these into a nested tree. A line with no
    active machines, or a machine with no active buttons, still appears
    (via LEFT JOIN) with null machine_id/button_id fields."""
    query = """
        SELECT
            pl.id AS line_id,
            pl.name AS line_name,
            pl.display_order AS line_display_order,
            m.id AS machine_id,
            m.name AS machine_name,
            m.display_order AS machine_display_order,
            b.id AS button_id,
            b.name AS button_name,
            b.event_type,
            b.ownership,
            b.fault_category,
            b.display_order AS button_display_order
        FROM public.production_lines AS pl
        LEFT JOIN public.machines AS m
            ON m.production_line_id = pl.id AND m.active = true
        LEFT JOIN public.buttons AS b
            ON b.machine_id = m.id AND b.active = true
        WHERE pl.active = true
        ORDER BY
            pl.display_order, pl.name,
            m.display_order, m.name,
            b.display_order, b.name;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return cursor.fetchall()


# ----------------------------------------------------------
# ACTIVE RUNS (ACROSS ALL LINES) + FORCE CLOSE
# ----------------------------------------------------------


def get_all_active_runs():
    query = """
        SELECT
            id,
            production_line,
            line_technician,
            shift,
            customer,
            product,
            status,
            started_at
        FROM public.production_runs
        WHERE status = 'Active'
        ORDER BY started_at DESC;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return cursor.fetchall()


def force_close_production_run(production_run_id, finished_at):
    """Atomic check-and-set: only closes a row that is still Active.
    This is the concurrency protection - if two managers force-close the
    same run at once, only one UPDATE matches a row (the partial unique
    index idx_unique_active_run_per_line already guarantees at most one
    Active row per line, and this WHERE clause guarantees at most one
    UPDATE can transition it away from Active). Returns None if no
    Active row matched (never existed, or already closed by someone
    else) - the caller does one cheap get_production_run_by_id lookup
    to tell those two cases apart for the HTTP response."""
    query = """
        UPDATE public.production_runs
        SET
            status = 'Cancelled',
            finished_at = %(finished_at)s
        WHERE id = %(production_run_id)s
          AND status = 'Active'
        RETURNING id, production_line, status, finished_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                {"production_run_id": production_run_id, "finished_at": finished_at},
            )
            closed = cursor.fetchone()

        connection.commit()

    return closed


# ----------------------------------------------------------
# AUDIT LOG
# ----------------------------------------------------------


def insert_audit_log(
    action,
    manager_name,
    record_type,
    record_id,
    previous_value=None,
    new_value=None,
    reason=None,
):
    query = """
        INSERT INTO public.management_audit_log (
            action, manager_name, record_type, record_id,
            previous_value, new_value, reason
        )
        VALUES (
            %(action)s, %(manager_name)s, %(record_type)s, %(record_id)s,
            %(previous_value)s, %(new_value)s, %(reason)s
        )
        RETURNING id, created_at;
    """

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                {
                    "action": action,
                    "manager_name": manager_name,
                    "record_type": record_type,
                    "record_id": str(record_id) if record_id is not None else None,
                    "previous_value": Json(previous_value) if previous_value is not None else None,
                    "new_value": Json(new_value) if new_value is not None else None,
                    "reason": reason,
                },
            )
            created = cursor.fetchone()

        connection.commit()

    return created


# ----------------------------------------------------------
# TECHNICIAN PERFORMANCE
# ----------------------------------------------------------


def get_technician_performance(filters=None):
    """Grouped by line_technician. Reuses the same filter builders (and
    therefore the same test-data exclusion) as the Dashboard section
    above. Callers should pass filters={"run_status": "Completed", ...}
    to restrict to finished runs only."""
    run_conditions, run_params = _run_conditions(filters)
    run_where = " AND ".join(run_conditions)

    hourly_conditions, hourly_params = _hourly_conditions(filters)
    hourly_where = " AND ".join(hourly_conditions)

    fault_conditions, fault_params = _fault_conditions(filters)
    fault_where = " AND ".join(fault_conditions)

    with get_database_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT
                    pr.line_technician,
                    COUNT(*) AS completed_runs,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM public.hourly_updates hu
                            WHERE hu.production_run_id = pr.id
                        )
                    ) AS runs_with_data,
                    ARRAY_AGG(DISTINCT pr.production_line) AS lines,
                    ARRAY_AGG(DISTINCT pr.shift) AS shifts,
                    ARRAY_AGG(DISTINCT pr.product) AS products,
                    ARRAY_AGG(DISTINCT pr.customer) AS customers,
                    ARRAY_AGG(pr.id ORDER BY pr.id) AS run_ids
                FROM public.production_runs AS pr
                WHERE {run_where}
                GROUP BY pr.line_technician;
                """,
                run_params,
            )
            run_rows = {row["line_technician"]: row for row in cursor.fetchall()}

            cursor.execute(
                f"""
                SELECT
                    pr.line_technician,
                    COALESCE(SUM(hu.expected_pallets), 0) AS expected_pallets,
                    COALESCE(SUM(hu.actual_pallets), 0) AS actual_pallets,
                    COALESCE(
                        SUM(
                            hu.expected_pallets
                            * pr.cases_per_pallet
                            * pr.packs_per_case
                            * pr.pack_weight_kg
                        ) / 1000.0,
                        0
                    ) AS expected_tonnes,
                    COALESCE(
                        SUM(
                            hu.actual_pallets
                            * pr.cases_per_pallet
                            * pr.packs_per_case
                            * pr.pack_weight_kg
                        ) / 1000.0,
                        0
                    ) AS actual_tonnes,
                    COALESCE(SUM(hu.planned_downtime_minutes), 0) AS planned_downtime_minutes
                FROM public.hourly_updates AS hu
                JOIN public.production_runs AS pr ON pr.id = hu.production_run_id
                WHERE {hourly_where}
                GROUP BY pr.line_technician;
                """,
                hourly_params,
            )
            hourly_rows = {row["line_technician"]: row for row in cursor.fetchall()}

            cursor.execute(
                f"""
                SELECT
                    pr.line_technician,
                    COALESCE(
                        SUM(
                            EXTRACT(
                                EPOCH FROM (COALESCE(de.resolved_at, NOW()) - de.opened_at)
                            ) / 60.0
                        ),
                        0
                    ) AS unplanned_downtime_minutes
                FROM public.downtime_events AS de
                JOIN public.production_runs AS pr ON pr.id = de.production_run_id
                WHERE {fault_where}
                GROUP BY pr.line_technician;
                """,
                fault_params,
            )
            fault_rows = {row["line_technician"]: row for row in cursor.fetchall()}

    empty_hourly = {
        "expected_pallets": 0,
        "actual_pallets": 0,
        "expected_tonnes": 0,
        "actual_tonnes": 0,
        "planned_downtime_minutes": 0,
    }

    results = []
    for technician, run_row in run_rows.items():
        hourly_row = hourly_rows.get(technician, empty_hourly)
        fault_row = fault_rows.get(technician)

        expected_pallets = float(hourly_row["expected_pallets"])
        actual_pallets = float(hourly_row["actual_pallets"])
        expected_tonnes = float(hourly_row["expected_tonnes"])
        actual_tonnes = float(hourly_row["actual_tonnes"])
        completed_runs = run_row["completed_runs"]
        runs_with_data = run_row["runs_with_data"]

        results.append({
            "line_technician": technician,
            "completed_runs": completed_runs,
            "expected_pallets": expected_pallets,
            "actual_pallets": actual_pallets,
            "expected_tonnes": expected_tonnes,
            "actual_tonnes": actual_tonnes,
            "output_gap_pallets": max(expected_pallets - actual_pallets, 0),
            "output_gap_tonnes": max(expected_tonnes - actual_tonnes, 0),
            "target_achievement_percent": (
                (actual_pallets / expected_pallets * 100)
                if expected_pallets > 0
                else None
            ),
            "planned_downtime_minutes": float(hourly_row["planned_downtime_minutes"]),
            "unplanned_downtime_minutes": (
                float(fault_row["unplanned_downtime_minutes"]) if fault_row else 0.0
            ),
            "data_completion_rate_percent": (
                (runs_with_data / completed_runs * 100) if completed_runs > 0 else None
            ),
            "lines": sorted(x for x in (run_row["lines"] or []) if x is not None),
            "shifts": sorted(x for x in (run_row["shifts"] or []) if x is not None),
            "products": sorted(x for x in (run_row["products"] or []) if x is not None),
            "customers": sorted(x for x in (run_row["customers"] or []) if x is not None),
            "run_ids": run_row["run_ids"] or [],
        })

    return results
