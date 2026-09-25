"""
Static, offline checks on migrations/0003_pulse_phase1_foundation.sql.
The file is only read as text - it is never executed or applied.
"""

from pathlib import Path
import re

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = PROJECT_ROOT / "migrations" / "0003_pulse_phase1_foundation.sql"


def executable_sql():
    """Migration text with every -- comment line removed, so documentation
    (the preflight queries and the manual rollback) is not mistaken for
    statements this migration runs."""
    lines = MIGRATION.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("--"))


def test_migration_is_one_transaction():
    sql = executable_sql().strip()
    assert sql.startswith("BEGIN;")
    assert sql.endswith("COMMIT;")


@pytest.mark.parametrize(
    "forbidden",
    [
        r"\bDROP\s+(TABLE|COLUMN|CONSTRAINT|INDEX)\b",
        r"\bDELETE\s+FROM\b",
        r"\bTRUNCATE\b",
        r"\bUPDATE\s+public\.",
        r"\bINSERT\s+INTO\b",
        r"\bRENAME\b",
    ],
)
def test_migration_is_additive_only(forbidden):
    assert not re.search(forbidden, executable_sql(), flags=re.IGNORECASE)


# ----------------------------------------------------------
# Static review: nothing destructive against existing production data
# ----------------------------------------------------------

EXISTING_TABLES = [
    "production_runs", "hourly_updates", "downtime_events", "engineering_updates",
    "production_lines", "machines", "buttons", "management_audit_log",
]


@pytest.mark.parametrize(
    "destructive",
    [
        r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b", r"\bDROP\s+INDEX\b",
        r"\bDROP\s+CONSTRAINT\b", r"\bDROP\s+SCHEMA\b", r"\bDROP\s+DATABASE\b",
        r"\bDELETE\s+FROM\b", r"\bTRUNCATE\b", r"\bUPDATE\s+public\.",
        r"\bINSERT\s+INTO\b", r"\bALTER\s+COLUMN\s+\w+\s+SET\s+NOT\s+NULL\b",
        r"\bRENAME\b", r"\bCASCADE\b",
    ],
)
def test_forward_migration_contains_no_destructive_operation(destructive):
    assert not re.search(destructive, executable_sql(), flags=re.IGNORECASE)


@pytest.mark.parametrize("table", EXISTING_TABLES)
def test_no_existing_table_is_dropped_or_emptied(table):
    sql = executable_sql()
    assert not re.search(rf"DROP\s+TABLE[^;]*{table}", sql, flags=re.IGNORECASE)
    assert not re.search(rf"TRUNCATE[^;]*{table}", sql, flags=re.IGNORECASE)
    assert not re.search(rf"DELETE\s+FROM[^;]*{table}", sql, flags=re.IGNORECASE)


def test_every_added_column_on_an_existing_table_is_nullable():
    """A NOT NULL column added to a populated table would fail or force
    a backfill. Every ADD COLUMN here is explicitly NULL."""
    sql = executable_sql()
    for match in re.finditer(r"ADD COLUMN (\w+) ([a-z0-9_]+(?:\([\d,]+\))?)([^,;]*)", sql):
        name, _type, tail = match.groups()
        # Only the new-table CREATE bodies use NOT NULL; ADD COLUMN must not.
        assert "NOT NULL" not in tail.upper(), f"ADD COLUMN {name} is NOT NULL"


def test_the_whole_migration_is_still_one_transaction():
    sql = executable_sql().strip()
    assert sql.startswith("BEGIN;")
    assert sql.endswith("COMMIT;")
    assert sql.count("BEGIN;") == 1
    assert sql.count("COMMIT;") == 1


# ----------------------------------------------------------
# Stage 6B3 corrections: live objects the migration must not re-create
# ----------------------------------------------------------


def test_the_live_hourly_updates_created_at_column_is_left_completely_alone():
    """It already exists as timestamptz NOT NULL DEFAULT now() with a
    real timestamp on every row. The migration must not add, drop,
    re-default, relax or backfill it."""
    sql = executable_sql()

    assert "ADD COLUMN created_at" not in sql
    assert "ALTER COLUMN created_at" not in sql
    assert "DROP COLUMN created_at" not in sql
    assert not re.search(r"UPDATE\s+public\.hourly_updates", sql, flags=re.IGNORECASE)


def test_period_boundaries_are_added_but_never_derived_from_created_at():
    """A submission time is not a period boundary."""
    sql = executable_sql()

    assert "ADD COLUMN period_started_at timestamptz NULL" in sql
    assert "ADD COLUMN period_ended_at timestamptz NULL" in sql
    assert not re.search(r"period_(started|ended)_at\s*=\s*created_at", sql)
    assert not re.search(r"created_at\s+AS\s+period_", sql, flags=re.IGNORECASE)


@pytest.mark.parametrize(
    "index_name",
    ["idx_hourly_updates_production_run_id", "idx_downtime_events_production_run_id"],
)
def test_pre_existing_indexes_are_not_recreated(index_name):
    """Both already exist live with exactly the required definition."""
    sql = executable_sql()

    assert f"CREATE INDEX {index_name}" not in sql
    assert f"DROP INDEX public.{index_name}" not in sql
    # The preflight must still name them, as REQUIRED EXISTING objects.
    assert index_name in MIGRATION.read_text(encoding="utf-8")


def test_no_if_not_exists_is_used_to_paper_over_drift():
    """Collisions must fail loudly, not be silently absorbed."""
    assert not re.search(r"IF NOT EXISTS", executable_sql(), flags=re.IGNORECASE)


def test_preflight_separates_required_existing_from_must_be_absent():
    text = MIGRATION.read_text(encoding="utf-8")

    assert "REQUIRED EXISTING objects" in text
    assert "must return ZERO rows" in text
    assert "CONFLICT, not a duplicate" in text
    absent_block = text[text.index("D. Objects this migration CREATES"):]
    absent_block = absent_block[: absent_block.index("All four must return zero rows")]
    assert "'created_at'" not in absent_block


# ----------------------------------------------------------
# Explicit numeric(10,2) -> numeric(14,4) widening
# ----------------------------------------------------------


@pytest.mark.parametrize("column", ["expected_pallets", "estimated_lost_minutes"])
def test_narrow_numeric_columns_are_widened_explicitly(column):
    """The integer loop skips them, so without this they would keep
    scale 2 and silently round the 4th decimal place."""
    sql = executable_sql()
    numeric_block = sql[sql.index("data_type = 'numeric'"):]

    assert f"('hourly_updates', '{column}')" in numeric_block


def test_the_numeric_widening_is_guarded_by_digits_and_scale_not_max():
    sql = executable_sql()
    numeric_block = sql[sql.index("data_type = 'numeric'"):]

    assert "trunc(abs(%I)) >= 10^10" in numeric_block
    assert "scale(%I) > 4" in numeric_block
    assert "RAISE EXCEPTION" in numeric_block
    assert "numeric(14,4)" in numeric_block


def test_the_numeric_widening_only_acts_on_columns_that_are_still_narrow():
    """Re-running after a successful apply must be a no-op."""
    sql = executable_sql()
    numeric_block = sql[sql.index("data_type = 'numeric'"):]

    assert "c.numeric_precision < 14" in numeric_block
    assert "c.numeric_scale < 4" in numeric_block


@pytest.mark.parametrize("column", ["packs_per_case", "cases_per_pallet", "pack_weight_kg", "oee"])
def test_columns_that_must_not_be_converted_are_absent_from_both_widening_lists(column):
    sql = executable_sql()

    assert f"('production_runs', '{column}')" not in sql
    assert f"('hourly_updates', '{column}')" not in sql


# ----------------------------------------------------------
# Security for the five new tables
# ----------------------------------------------------------

NEW_TABLES = [
    "planned_downtime_events",
    "production_run_xray_counts",
    "changeovers",
    "weekly_tonnage_targets",
    "hmi_idempotency_keys",
]


@pytest.mark.parametrize("table", NEW_TABLES)
def test_every_new_table_enables_row_level_security(table):
    assert re.search(
        rf"ALTER TABLE public\.{table}\s+ENABLE ROW LEVEL SECURITY;",
        executable_sql(),
    )


@pytest.mark.parametrize("table", NEW_TABLES)
def test_every_new_table_revokes_direct_api_access(table):
    sql = executable_sql()
    revoke_block = sql[sql.index("REVOKE ALL PRIVILEGES ON TABLE"):]
    revoke_block = revoke_block[: revoke_block.index(";") + 1]

    assert f"public.{table}" in revoke_block
    assert "FROM anon, authenticated, PUBLIC" in revoke_block


def test_no_permissive_policy_is_created_for_the_new_tables():
    """RLS with no policy is deny-all; a permissive policy would undo it."""
    assert not re.search(r"CREATE POLICY", executable_sql(), flags=re.IGNORECASE)


def test_sequence_privileges_are_revoked_too():
    sql = executable_sql()
    assert "REVOKE ALL PRIVILEGES ON SEQUENCE" in sql
    assert "relkind = 'S'" in sql


def test_existing_table_grants_are_not_changed_by_this_migration():
    """The TRUNCATE clean-up is a separate hardening migration."""
    sql = executable_sql()
    for existing in (
        "production_runs", "hourly_updates", "downtime_events",
        "engineering_updates", "production_lines", "machines",
        "buttons", "management_audit_log",
    ):
        assert not re.search(rf"REVOKE[^;]*\bpublic\.{existing}\b", sql, flags=re.DOTALL)
        assert not re.search(rf"GRANT[^;]*\bpublic\.{existing}\b", sql, flags=re.DOTALL)


def test_truncate_followup_is_documented_but_not_performed():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "TRUNCATE is currently granted to anon and authenticated" in text
    assert "separate security-hardening" in text
    assert "REVOKE TRUNCATE" not in executable_sql()


def test_migration_history_drift_is_documented_but_not_fabricated():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "supabase_migrations.schema_migrations" in text
    assert "NOT insert fabricated history rows" in text
    assert "supabase_migrations" not in executable_sql()


# ----------------------------------------------------------
# Rollback must match the corrected forward migration
# ----------------------------------------------------------


def rollback_block():
    text = MIGRATION.read_text(encoding="utf-8")
    start = text.index("-- ROLLBACK (manual")
    return text[start: text.index("\nBEGIN;")]


@pytest.mark.parametrize(
    "must_not_drop",
    [
        "DROP COLUMN created_at",
        "DROP INDEX public.idx_hourly_updates_production_run_id",
        "DROP INDEX public.idx_downtime_events_production_run_id",
    ],
)
def test_rollback_never_touches_pre_existing_objects(must_not_drop):
    assert must_not_drop not in rollback_block()


def test_rollback_still_removes_everything_this_migration_creates():
    block = rollback_block()
    for table in NEW_TABLES:
        assert f"DROP TABLE public.{table};" in block
    for column in (
        "period_started_at", "period_ended_at", "period_minutes", "shift",
        "shift_window_start", "line_technician", "other_loss_reason", "submitted_via",
    ):
        assert f"DROP COLUMN {column}" in block
    assert "ALTER TABLE public.production_runs DROP COLUMN format;" in block


def test_rollback_does_not_alter_history_or_unrelated_objects():
    block = rollback_block()

    # It may *mention* history in the prose that forbids touching it,
    # but no statement may act on it.
    assert not re.search(
        r"(INSERT|UPDATE|DELETE)[^;]*supabase_migrations", block, flags=re.IGNORECASE
    )
    assert not re.search(r"(DROP|ALTER)[^;]*management_audit_log", block, flags=re.IGNORECASE)
    assert not re.search(r"^\s*--\s+(REVOKE|GRANT)\s", block, flags=re.MULTILINE)


def test_integer_widening_is_limited_to_integer_types():
    sql = executable_sql()
    assert "c.data_type IN ('smallint', 'integer', 'bigint')" in sql
    assert "numeric(14,4)" in sql
    assert "double precision" not in sql


def test_constraint_on_existing_rows_is_not_validated_retroactively():
    assert "CHECK (pallets_completed >= 0) NOT VALID" in executable_sql()


# ----------------------------------------------------------
# Idempotency retention (90 days)
# ----------------------------------------------------------


def test_idempotency_rows_carry_both_a_creation_and_an_expiry_time():
    sql = executable_sql()
    assert re.search(r"created_at\s+timestamptz NOT NULL DEFAULT now\(\)", sql)
    assert re.search(
        r"expires_at\s+timestamptz NOT NULL DEFAULT \(now\(\) \+ interval '90 days'\)", sql
    )


def test_expiry_is_set_by_the_database_not_the_client():
    """Both timestamps are column DEFAULTs, so an HMI request cannot
    supply its own expiry and shorten its duplicate protection."""
    sql = executable_sql()
    table = sql[sql.index("CREATE TABLE public.hmi_idempotency_keys"):]
    table = table[: table.index(");") + 2]

    assert "DEFAULT now()" in table
    assert "DEFAULT (now() + interval '90 days')" in table
    assert "CHECK (expires_at > created_at)" in table


def test_an_index_supports_the_expiry_sweep():
    assert re.search(
        r"CREATE INDEX idx_hmi_idempotency_keys_expires_at\s+"
        r"ON public\.hmi_idempotency_keys USING btree \(expires_at\)",
        executable_sql(),
    )


def test_retention_needs_no_extension_and_no_pg_cron():
    sql = executable_sql().lower()
    assert "pg_cron" not in sql
    assert "create extension" not in sql


def test_the_migration_itself_removes_no_idempotency_rows():
    """Retention is a separate, explicitly-run maintenance operation -
    applying the migration must not delete anything."""
    assert "DELETE" not in executable_sql().upper()


def test_one_open_changeover_per_line_and_one_open_planned_stop_per_run():
    sql = executable_sql()
    assert re.search(
        r"UNIQUE INDEX uq_changeovers_one_open_per_line\s+ON public\.changeovers \(production_line\)\s+WHERE status = 'Open'",
        sql,
    )
    assert re.search(
        r"UNIQUE INDEX uq_planned_downtime_one_open_per_run\s+ON public\.planned_downtime_events "
        r"\(production_run_id\)\s+WHERE ended_at IS NULL",
        sql,
    )


def test_xray_row_requires_count_or_reason_and_no_waste_when_unavailable():
    sql = executable_sql()
    assert "chk_xray_available_or_reason" in sql
    assert "chk_xray_waste_only_when_available" in sql
    assert "xray_pack_count IS NULL OR xray_pack_count >= 0" in sql


def test_maintenance_preventable_allows_exactly_yes_no_unsure():
    assert "CHECK (maintenance_preventable IN ('Yes', 'No', 'Unsure'))" in executable_sql()


def test_weekly_targets_are_positive_monday_scoped_and_unique():
    sql = executable_sql()
    assert "CHECK (target_tonnes > 0)" in sql
    assert "CHECK (EXTRACT(ISODOW FROM week_start) = 1)" in sql
    assert "uq_weekly_target_per_scope" in sql


def test_migration_documents_preflight_and_rollback():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "PREFLIGHT" in text
    assert "ROLLBACK" in text
    assert "NOT applied" in text


def test_code_and_migration_agree_on_new_column_names():
    sql = executable_sql()
    database_source = (PROJECT_ROOT / "src" / "database.py").read_text(encoding="utf-8")
    for column in (
        "period_started_at", "period_ended_at", "other_loss_reason", "submitted_via",
        "report_note", "reported_via", "maintenance_preventable", "machine_id", "button_id",
    ):
        assert column in sql, column
        assert column in database_source, column
