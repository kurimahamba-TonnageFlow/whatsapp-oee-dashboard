"""
Static, offline checks on migrations/0004_fixed_hour_reporting.sql.
The file is only read as text - it is never executed or applied.
"""

from pathlib import Path
import re

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = PROJECT_ROOT / "migrations" / "0004_fixed_hour_reporting.sql"
NEW_TABLES = [
    "run_target_speed_changes", "line_stoppages", "fault_acknowledgements",
    "line_stoppage_reclassifications", "run_next_step_legacy_baseline",
]


def executable_sql():
    lines = MIGRATION.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("--"))


def test_migration_is_one_transaction():
    sql = executable_sql().strip()
    assert sql.startswith("BEGIN;")
    assert sql.endswith("COMMIT;")


@pytest.mark.parametrize(
    "destructive",
    [
        r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b", r"\bDROP\s+INDEX\b", r"\bDROP\s+CONSTRAINT\b",
        r"\bDELETE\s+FROM\b", r"\bTRUNCATE\b", r"\bUPDATE\s+public\.",
        r"\bINSERT\s+INTO\s+public\.(?!run_next_step_legacy_baseline\b)",
        r"\bSET\s+NOT\s+NULL\b", r"\bRENAME\b",
    ],
)
def test_forward_migration_is_additive_only(destructive):
    assert not re.search(destructive, executable_sql(), flags=re.IGNORECASE)


def test_every_column_added_to_an_existing_table_is_nullable():
    for match in re.finditer(r"ADD COLUMN (\w+) ([^,;\n]+)", executable_sql()):
        assert "NOT NULL" not in match.group(2), match.group(0)


def test_one_reading_per_run_per_clock_hour():
    sql = executable_sql()
    assert "ADD COLUMN hour_start timestamptz NULL" in sql
    assert re.search(
        r"CREATE UNIQUE INDEX uq_hourly_updates_one_reading_per_run_hour\s+ON public\.hourly_updates "
        r"\(production_run_id, hour_start\)\s+WHERE hour_start IS NOT NULL",
        sql,
    )


def test_one_open_line_stop_per_line_and_other_needs_a_reason():
    sql = executable_sql()
    assert "uq_line_stoppages_one_open_per_line" in sql
    assert "CHECK (kind IN ('changeover', 'other', 'handover', 'restart_delay', 'not_scheduled'))" in sql
    assert re.search(
        r"CREATE UNIQUE INDEX uq_line_stoppages_one_next_step_per_run\s+ON public\.line_stoppages "
        r"\(previous_production_run_id\)\s+WHERE previous_production_run_id IS NOT NULL "
        r"AND follows_stoppage_id IS NULL",
        sql,
    )
    assert "CHECK (kind <> 'restart_delay' OR follows_stoppage_id IS NOT NULL)" in sql
    assert "uq_line_stoppages_one_follower" in sql
    assert "chk_line_stoppage_physical_end" in sql
    assert "physical_ended_at           timestamptz NULL" in sql
    assert "kind <> 'other' OR length(btrim(COALESCE(reason, ''))) > 0" in sql


def test_speed_changes_keep_both_speeds_and_a_reason():
    sql = executable_sql()
    for column in ("previous_speed_ppm", "new_speed_ppm", "reason", "changed_by", "effective_at"):
        assert re.search(rf"{column}\s+\S+ NOT NULL", sql), column


def test_changeovers_keep_one_source_and_the_legacy_invariant():
    sql = executable_sql()
    assert "chk_changeover_has_one_source" in sql
    assert "chk_changeover_in_run_has_new_configuration" in sql
    assert "line_stoppage_id bigint NULL UNIQUE REFERENCES public.line_stoppages (id)" in sql


def test_escalation_updates_the_fault_rather_than_adding_one():
    sql = executable_sql()
    assert "ADD COLUMN escalation_count integer NULL" in sql
    assert "CREATE TABLE public.fault_acknowledgements" in sql


@pytest.mark.parametrize("table", NEW_TABLES)
def test_every_new_table_is_locked_down_like_0003(table):
    sql = executable_sql()
    assert f"ALTER TABLE public.{table}" in sql and "ENABLE ROW LEVEL SECURITY" in sql
    revoke = re.search(r"REVOKE ALL PRIVILEGES ON TABLE(.+?)FROM anon, authenticated, PUBLIC;", sql, re.S)
    assert revoke and f"public.{table}" in revoke.group(1)
    assert "CREATE POLICY" not in sql


def test_documents_preflight_apply_and_rollback_and_is_not_applied():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "NOT APPLIED" in text
    assert "PREFLIGHT" in text and "ROLLBACK" in text and "psql" in text


def test_code_and_migration_agree_on_names():
    sql = executable_sql()
    code = (PROJECT_ROOT / "src" / "database.py").read_text(encoding="utf-8")
    for name in ("hour_start", "run_target_speed_changes", "line_stoppages", "fault_acknowledgements",
                 "line_stoppage_id", "escalation_count", "last_escalated_at", "last_escalated_by"):
        assert name in sql and name in code, name


def test_the_only_rows_written_are_legacy_baseline_markers_for_ended_runs():
    sql = executable_sql()
    inserts = re.findall(r"INSERT INTO public\.(\w+)", sql)
    assert inserts == ["run_next_step_legacy_baseline"]
    baseline = re.search(
        r"INSERT INTO public\.run_next_step_legacy_baseline.*?;", sql, flags=re.S
    ).group(0)
    assert "FROM public.production_runs" in baseline
    assert "status IS DISTINCT FROM 'Active'" in baseline      # still-Active runs are NOT baselined
    assert "finished_at IS NOT NULL" in baseline
    assert "ON CONFLICT (production_run_id) DO NOTHING" in baseline   # re-runnable, never moves a marker
    # No line stoppage (i.e. no next step) is fabricated for a historical run.
    assert not re.search(r"INSERT INTO public\.line_stoppages", sql)


def test_the_baseline_runs_after_the_tables_it_protects_in_the_same_transaction():
    sql = executable_sql()
    assert sql.index("CREATE TABLE public.line_stoppages") < sql.index(
        "INSERT INTO public.run_next_step_legacy_baseline"
    ) < sql.rindex("COMMIT;")
    assert "production_run_id   bigint PRIMARY KEY REFERENCES public.production_runs (id)" in sql


def test_reclassifications_keep_previous_and_new_classification_who_when_and_why():
    sql = executable_sql()
    for column in ("previous_kind", "new_kind", "changed_by", "changed_at", "note"):
        assert re.search(rf"{column}\s+\S+ NOT NULL", sql), column
    assert "chk_reclassification_changes_something" in sql
    assert "chk_reclassification_note_present" in sql


def test_preflight_covers_the_baseline_and_rollback_drops_the_new_tables():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "LEGACY BASELINE PREFLIGHT" in text
    assert "DROP TABLE public.run_next_step_legacy_baseline;" in text
    assert "DROP TABLE public.line_stoppage_reclassifications;" in text
