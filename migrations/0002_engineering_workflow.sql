-- ==========================================================
-- TONNAGEFLOW PULSE
-- Migration 0002: Engineering workflow
-- ==========================================================
--
-- Adds the columns Stage 5A's Engineering API needs to
-- downtime_events and engineering_updates. Purely additive:
--   - Every new column is nullable (or has a safe DEFAULT), so every
--     existing row in both tables (currently 4 downtime_events rows,
--     5 engineering_updates rows - see
--     docs/management_migration_verification.md) remains valid,
--     unchanged, and fully queryable exactly as it is today.
--   - No existing column, table, row, index or constraint is altered
--     or dropped.
--   - This migration does not touch migrations/0001_management_area.sql
--     or any table it created.
--
-- LIVE-SCHEMA PREFLIGHT (verified via a read-only Supabase check
-- before this correction, ahead of applying anything):
--   - engineering_updates.created_at ALREADY EXISTS in the live
--     database: timestamp with time zone, NOT NULL, DEFAULT now().
--     This migration therefore does NOT add, alter, backfill, rename
--     or otherwise touch that column in any way - see the note further
--     down instead of an ALTER TABLE statement for it.
--   - engineering_updates already has CHECK constraint
--     chk_engineering_update_type permitting exactly 'Investigation',
--     'Follow Up', 'Resolution' - the same three values
--     src/database.py's CLI-era code and Stage 5A's Engineering API
--     both use ('Follow Up' for interim updates, 'Resolution' for the
--     final closing update). This migration does not need to, and
--     does not, touch that constraint.
--
-- NOT applied automatically by any script in this repo, and NOT
-- applied to Supabase during Stage 5A. Review this file, then apply
-- it only once approved (see the "how this migration would be
-- applied" note in the Stage 5A report).

BEGIN;

-- ----------------------------------------------------------
-- downtime_events: when an engineer accepted / started work
-- ----------------------------------------------------------
-- Nullable - NULL means "not yet accepted", true for every existing
-- row (the CLI never recorded this). Set once, on first Accept
-- (src/database.py: accept_engineering_fault uses
-- COALESCE(accepted_at, ...) so a repeat Accept by the same engineer
-- never overwrites the original time).

ALTER TABLE public.downtime_events
    ADD COLUMN accepted_at timestamptz NULL;

-- ----------------------------------------------------------
-- engineering_updates: repair classification + Machine Setting detail
-- + optional notes
-- ----------------------------------------------------------
-- All nullable, so every existing row (created by the CLI, which has
-- no concept of these fields) stays exactly as valid as it is today -
-- it will simply read back with these columns NULL.
--
-- The CHECK constraint on repair_classification permits NULL (Postgres
-- only evaluates a CHECK against non-NULL values), so it does not
-- reject any existing row.

ALTER TABLE public.engineering_updates
    ADD COLUMN repair_classification text NULL,
    ADD COLUMN setting_name text NULL,
    ADD COLUMN previous_value text NULL,
    ADD COLUMN new_value text NULL,
    ADD COLUMN reason_for_change text NULL,
    ADD COLUMN affected_products_or_formats text NULL,
    ADD COLUMN notes text NULL;

ALTER TABLE public.engineering_updates
    ADD CONSTRAINT chk_engineering_update_repair_classification
        CHECK (repair_classification IN ('Mechanical', 'Machine Setting'));

-- ----------------------------------------------------------
-- engineering_updates.created_at - DELIBERATELY NOT TOUCHED
-- ----------------------------------------------------------
-- A read-only Supabase preflight (run ahead of applying this
-- migration) confirmed engineering_updates.created_at already exists
-- in the live schema as:
--     timestamp with time zone, NOT NULL, DEFAULT now()
-- An earlier draft of this migration assumed this column did not yet
-- exist and proposed adding it nullable (to avoid fabricating
-- historical timestamps). That assumption was wrong for THIS
-- database, so that ALTER TABLE has been removed entirely. There is
-- no statement for created_at anywhere in this migration:
--   - Not added (it already exists).
--   - Not altered (its type, nullability and default are already
--     exactly what src/database.py's add_engineering_repair_update()
--     and close_engineering_fault() rely on - both omit created_at
--     from their INSERT column list and depend on this existing
--     DEFAULT now()).
--   - Not backfilled (no existing row's created_at is touched).
--   - Not renamed.
-- src/engineering_api.py's EngineeringFaultRepairUpdate.created_at is
-- a required (non-nullable) field, matching this verified NOT NULL
-- guarantee - every row in engineering_updates, historical or new,
-- already has a real timestamp.

-- ----------------------------------------------------------
-- engineering_updates.update_type / chk_engineering_update_type -
-- DELIBERATELY NOT TOUCHED
-- ----------------------------------------------------------
-- Also confirmed by the same preflight: the existing CHECK constraint
-- chk_engineering_update_type already permits 'Investigation',
-- 'Follow Up' and 'Resolution' (3 existing 'Investigation' rows, 2
-- existing 'Resolution' rows). Stage 5A's Engineering API writes
-- 'Follow Up' for interim /updates calls and 'Resolution' for /close
-- calls - both already-permitted values - so this migration makes no
-- change to update_type or its constraint.

COMMIT;
