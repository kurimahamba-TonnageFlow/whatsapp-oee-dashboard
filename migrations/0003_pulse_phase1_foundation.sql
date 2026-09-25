-- ==========================================================
-- TONNAGEFLOW PULSE
-- Migration 0003: Phase 1 data foundation (Stage 6B1)
-- ==========================================================
--
-- Adds what the React HMI capture endpoints and the protected
-- management dashboard need:
--   1. hourly_updates: real timestamps, period boundaries, shift,
--      technician, loss reason, source; decimal pallet support.
--   2. production_runs: `format`; decimal pallet progress support.
--   3. downtime_events: machine/button links, report note, source,
--      maintenance-preventability classification.
--   4. New tables: planned_downtime_events, production_run_xray_counts,
--      changeovers, weekly_tonnage_targets, hmi_idempotency_keys.
--   5. Server-enforced idempotency for every HMI write (Stage 6B2):
--      each write claims its client-generated Idempotency-Key in the
--      SAME transaction as the business rows it creates, and stores the
--      response it returned, so a double tap or a retry after a timeout
--      replays the original result instead of writing twice.
--
-- CORRECTED after the Stage 6B3 read-only preflight against the live
-- database. Three objects this migration originally created already
-- existed, so it would have aborted. See "LIVE STATE" below.
--
-- ADDITIVE ONLY:
--   - Every new column is nullable, so every existing row stays valid
--     and reads back exactly as before with the new columns NULL.
--   - No row is deleted, rewritten or backfilled with invented values.
--   - hourly_updates.created_at is NOT touched. It already exists live
--     as timestamptz NOT NULL DEFAULT now(), and every existing row
--     carries a real submission timestamp. What legacy rows lack is a
--     captured period START and END, which is why they stay out of any
--     report that needs a reliable production period. period_started_at
--     and period_ended_at are NEVER derived from created_at - a
--     submission time is not a period boundary.
--   - Integer pallet/pack columns are widened to numeric(14,4) ONLY
--     if they are currently smallint/integer/bigint. That conversion
--     is exact (every integer is representable), so no stored value
--     changes. Floating-point columns are deliberately NOT converted
--     (that could round stored values) - see PREFLIGHT below.
--   - Two columns that are already numeric but too narrow
--     (hourly_updates.expected_pallets and estimated_lost_minutes,
--     live numeric(10,2)) are widened explicitly to numeric(14,4).
--     Both precision and scale only grow, and a guard proves every
--     stored value fits before the conversion runs.
--   - hourly_updates.oee NOT NULL (if present) is relaxed, because the
--     React HMI does not capture reported OEE. Relaxing NOT NULL never
--     changes data.
--   - The new CHECK on an existing column (pallets_completed) is added
--     NOT VALID: enforced for every new/updated row, and never fails
--     the migration because of an unknown historical row.
--   - The five NEW tables get RLS enabled with no policies, and ALL
--     privileges revoked from anon, authenticated and PUBLIC. Grants on
--     pre-existing tables are NOT changed here.
--
-- LIVE STATE this migration now expects to find (Stage 6B3 preflight):
--   - hourly_updates.created_at            EXISTS (timestamptz NOT NULL
--                                          DEFAULT now()) - left alone
--   - idx_hourly_updates_production_run_id EXISTS - not re-created
--   - idx_downtime_events_production_run_id EXISTS - not re-created
--   Everything else this migration creates must be ABSENT.
--
-- FOLLOW-UP REQUIRED (deliberately NOT done here):
--   1. TRUNCATE is currently granted to anon and authenticated on every
--      pre-existing public application table (production_runs,
--      hourly_updates, downtime_events, engineering_updates,
--      production_lines, machines, buttons, management_audit_log).
--      RLS does not restrict TRUNCATE. A separate security-hardening
--      migration must REVOKE TRUNCATE (and any other unintended
--      privilege) from anon and authenticated on those tables. It is
--      kept out of this migration so a schema change and a permission
--      change can be reviewed, applied and rolled back independently.
--   2. Migration history drift: supabase_migrations.schema_migrations
--      records only 20260903175836 and 20260903190445. Migrations 0001
--      and 0002 are NOT recorded, yet all of their objects exist live -
--      they were applied outside tracked history. This migration does
--      NOT insert fabricated history rows and does NOT mark 0001 or
--      0002 as applied. A later reconciliation should decide whether to
--      adopt the CLI history properly (for example by baselining) - a
--      decision to take deliberately, not as a side effect of applying
--      this file.
--
-- NOT applied automatically by any script in this repo, and NOT
-- applied during Stage 6B1. Review this file, run the read-only
-- PREFLIGHT, then apply only once approved.
--
-- ----------------------------------------------------------
-- PREFLIGHT (read-only - run and review BEFORE applying)
-- ----------------------------------------------------------
-- Run every query below and compare with the EXPECTED note. This
-- preflight distinguishes objects that MUST already exist from objects
-- that MUST be absent; anything else is unexpected drift - stop.
--
-- A. REQUIRED EXISTING objects (relied on, and NOT created here).
--    Each query must return exactly one row:
--
--    -- EXPECTED: timestamptz / NO / now()
--    SELECT data_type, is_nullable, column_default
--    FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'hourly_updates'
--      AND column_name = 'created_at';
--
--    -- EXPECTED: exactly these two index definitions
--    SELECT indexname, indexdef FROM pg_indexes
--    WHERE schemaname = 'public'
--      AND indexname IN ('idx_hourly_updates_production_run_id',
--                        'idx_downtime_events_production_run_id');
--    --   idx_hourly_updates_production_run_id:
--    --     CREATE INDEX ... ON public.hourly_updates USING btree (production_run_id)
--    --   idx_downtime_events_production_run_id:
--    --     CREATE INDEX ... ON public.downtime_events USING btree (production_run_id)
--    If a definition differs, that is a CONFLICT, not a duplicate - stop.
--
-- B. Column types this migration may widen, and anything depending on
--    them (a dependent view blocks ALTER ... TYPE):
--
--    SELECT table_name, column_name, data_type, numeric_precision,
--           numeric_scale, is_nullable
--    FROM information_schema.columns
--    WHERE table_schema = 'public'
--      AND table_name IN ('hourly_updates', 'production_runs', 'downtime_events')
--    ORDER BY table_name, ordinal_position;
--
--    -- EXPECTED: zero rows. A view or matview on a target column
--    -- blocks ALTER ... TYPE.
--    SELECT DISTINCT view_name, table_name
--    FROM information_schema.view_table_usage
--    WHERE table_schema = 'public'
--      AND table_name IN ('hourly_updates', 'production_runs');
--
--    If any listed pallet/pack column is `real` or `double precision`,
--    STOP and decide separately - this migration leaves it unchanged.
--
-- C. The two numeric columns widened explicitly must fit numeric(14,4).
--    MAX() alone is NOT sufficient - check digits and scale separately.
--
--    -- EXPECTED: numeric / 10 / 2 for both (the pre-migration state)
--    SELECT column_name, data_type, numeric_precision, numeric_scale
--    FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'hourly_updates'
--      AND column_name IN ('expected_pallets', 'estimated_lost_minutes');
--
--    -- EXPECTED: 0 for every count
--    SELECT
--      count(*) FILTER (WHERE trunc(abs(expected_pallets)) >= 10^10)       AS ep_digits,
--      count(*) FILTER (WHERE scale(expected_pallets) > 4)                 AS ep_scale,
--      count(*) FILTER (WHERE trunc(abs(estimated_lost_minutes)) >= 10^10) AS elm_digits,
--      count(*) FILTER (WHERE scale(estimated_lost_minutes) > 4)           AS elm_scale
--    FROM public.hourly_updates;
--
-- D. Objects this migration CREATES - every query must return ZERO rows:
--
--    SELECT table_name, column_name FROM information_schema.columns
--    WHERE table_schema = 'public' AND (
--        (table_name = 'hourly_updates' AND column_name IN (
--            'period_started_at', 'period_ended_at', 'period_minutes',
--            'shift', 'shift_window_start', 'line_technician',
--            'other_loss_reason', 'submitted_via'))
--     OR (table_name = 'production_runs' AND column_name = 'format')
--     OR (table_name = 'downtime_events' AND column_name IN ('machine_id',
--            'button_id', 'reported_via', 'report_note', 'maintenance_preventable'))
--    );
--    NOTE: created_at is intentionally NOT in this list - it is a
--    REQUIRED EXISTING object (section A), not a new column.
--
--    SELECT table_name FROM information_schema.tables
--    WHERE table_schema = 'public' AND table_name IN ('planned_downtime_events',
--        'production_run_xray_counts', 'changeovers', 'weekly_tonnage_targets',
--        'hmi_idempotency_keys');
--
--    SELECT conname FROM pg_constraint WHERE conname IN (
--        'chk_hourly_updates_submitted_via',
--        'chk_hourly_updates_pallets_completed_non_negative',
--        'chk_downtime_events_reported_via',
--        'chk_downtime_events_maintenance_preventable',
--        'chk_idempotency_key_format',
--        'chk_idempotency_expiry_after_creation');
--
--    SELECT indexname FROM pg_indexes WHERE schemaname = 'public'
--      AND indexname IN ('idx_hourly_updates_period_ended_at',
--        'idx_hourly_updates_shift_window_start',
--        'idx_production_runs_line_started_at', 'idx_downtime_events_opened_at',
--        'uq_planned_downtime_one_open_per_run', 'idx_planned_downtime_started_at',
--        'uq_xray_one_run_completion_per_run', 'uq_xray_one_shift_end_per_run_shift',
--        'idx_xray_captured_at', 'uq_changeovers_one_open_per_line',
--        'uq_weekly_target_per_scope', 'idx_hmi_idempotency_keys_created_at',
--        'idx_hmi_idempotency_keys_expires_at');
--
--    All four must return zero rows. This migration deliberately does
--    not use IF NOT EXISTS, so an unexpected pre-existing object fails
--    loudly instead of being silently kept.
--
-- ----------------------------------------------------------
-- ROLLBACK (manual, only if nothing has been written to the new
-- objects yet - these statements discard their data)
-- ----------------------------------------------------------
--    BEGIN;
--    -- Dropping a table drops its RLS state, policies, grants and
--    -- identity sequences with it, so the security block needs no
--    -- separate reversal.
--    DROP TABLE public.hmi_idempotency_keys;
--    DROP TABLE public.weekly_tonnage_targets;
--    DROP TABLE public.changeovers;
--    DROP TABLE public.production_run_xray_counts;
--    DROP TABLE public.planned_downtime_events;
--    DROP INDEX public.idx_downtime_events_opened_at;
--    ALTER TABLE public.downtime_events
--        DROP COLUMN maintenance_preventable, DROP COLUMN report_note,
--        DROP COLUMN reported_via, DROP COLUMN button_id, DROP COLUMN machine_id;
--    DROP INDEX public.idx_production_runs_line_started_at;
--    ALTER TABLE public.production_runs DROP COLUMN format;
--    DROP INDEX public.idx_hourly_updates_shift_window_start;
--    DROP INDEX public.idx_hourly_updates_period_ended_at;
--    ALTER TABLE public.hourly_updates
--        DROP CONSTRAINT chk_hourly_updates_pallets_completed_non_negative,
--        DROP COLUMN submitted_via, DROP COLUMN other_loss_reason,
--        DROP COLUMN line_technician, DROP COLUMN shift_window_start, DROP COLUMN shift,
--        DROP COLUMN period_minutes, DROP COLUMN period_ended_at,
--        DROP COLUMN period_started_at;
--    COMMIT;
--    (Dropping a column also drops its column-level CHECK constraints.)
--
--    This rollback deliberately does NOT:
--      * drop hourly_updates.created_at - it pre-dates this migration
--        and holds a real timestamp on every existing row;
--      * drop idx_hourly_updates_production_run_id or
--        idx_downtime_events_production_run_id - both pre-date this
--        migration and are not created by it;
--      * touch supabase_migrations.schema_migrations;
--      * touch any grant or RLS setting on a pre-existing table.
--
--    The numeric widenings (integer -> numeric(14,4), and
--    numeric(10,2) -> numeric(14,4) for expected_pallets and
--    estimated_lost_minutes) and the relaxed oee NOT NULL are
--    intentionally NOT reversed: once a fractional value such as 3.75
--    or a 4-dp value exists, narrowing back would round stored data.

BEGIN;

-- ----------------------------------------------------------
-- 1. hourly_updates
-- ----------------------------------------------------------

-- created_at is deliberately NOT added here. The live database already
-- has hourly_updates.created_at timestamptz NOT NULL DEFAULT now(), and
-- every existing row carries a timestamp (confirmed by the Stage 6B3
-- read-only preflight). This migration leaves that column exactly as it
-- is: not dropped, not relaxed, not re-defaulted and not backfilled.
ALTER TABLE public.hourly_updates
    ADD COLUMN period_started_at timestamptz NULL,
    ADD COLUMN period_ended_at timestamptz NULL,
    ADD COLUMN period_minutes numeric(14,4) NULL,
    ADD COLUMN shift text NULL,
    -- Start of the operational shift instance the output belongs to: the
    -- run's recorded shift, anchored on the period END (see
    -- src/factory_time.py operational_shift_window). Shift, factory-day
    -- and weekly reports select hourly output by this, so a period that
    -- ends at 06:00 / 14:00 / 22:00 stays with the shift that produced it.
    ADD COLUMN shift_window_start timestamptz NULL,
    ADD COLUMN line_technician text NULL,
    ADD COLUMN other_loss_reason text NULL,
    ADD COLUMN submitted_via text NULL
        CONSTRAINT chk_hourly_updates_submitted_via
            CHECK (submitted_via IN ('cli', 'react_hmi'));

ALTER TABLE public.hourly_updates
    ADD CONSTRAINT chk_hourly_updates_pallets_completed_non_negative
        CHECK (pallets_completed >= 0) NOT VALID;

-- idx_hourly_updates_production_run_id is NOT created here: it already
-- exists live with exactly the required definition
--   CREATE INDEX ... ON public.hourly_updates USING btree (production_run_id)
-- and is listed in the PREFLIGHT as a REQUIRED EXISTING object. No
-- IF NOT EXISTS is used anywhere in this migration, so a genuinely
-- unexpected object still fails loudly.

CREATE INDEX idx_hourly_updates_period_ended_at
    ON public.hourly_updates USING btree (period_ended_at);

CREATE INDEX idx_hourly_updates_shift_window_start
    ON public.hourly_updates USING btree (shift_window_start);

-- ----------------------------------------------------------
-- 2. production_runs
-- ----------------------------------------------------------

ALTER TABLE public.production_runs
    ADD COLUMN format text NULL;

CREATE INDEX idx_production_runs_line_started_at
    ON public.production_runs USING btree (production_line, started_at DESC);

-- ----------------------------------------------------------
-- Decimal pallets: exact integer -> numeric(14,4) widening, only for
-- columns that are currently integer types.
-- ----------------------------------------------------------

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns AS c
        WHERE c.table_schema = 'public'
          AND c.data_type IN ('smallint', 'integer', 'bigint')
          AND (c.table_name, c.column_name) IN (
              VALUES
                  ('hourly_updates', 'pallets_completed'),
                  ('hourly_updates', 'actual_pallets'),
                  ('hourly_updates', 'expected_pallets'),
                  ('hourly_updates', 'pallets_remaining'),
                  ('hourly_updates', 'expected_packs'),
                  ('hourly_updates', 'actual_packs'),
                  ('hourly_updates', 'production_variance_packs'),
                  ('hourly_updates', 'estimated_lost_packs'),
                  ('hourly_updates', 'estimated_lost_minutes'),
                  ('hourly_updates', 'planned_downtime_minutes'),
                  ('production_runs', 'pallets_remaining'),
                  ('production_runs', 'total_pallets_completed'),
                  ('production_runs', 'potential_overrun_pallets'),
                  ('production_runs', 'confirmed_overrun_pallets')
          )
    LOOP
        RAISE NOTICE 'Widening %.% to numeric(14,4)', target.table_name, target.column_name;
        EXECUTE format(
            'ALTER TABLE public.%I ALTER COLUMN %I TYPE numeric(14,4) USING %I::numeric(14,4)',
            target.table_name, target.column_name, target.column_name
        );
    END LOOP;
END
$$;

-- ----------------------------------------------------------
-- Decimal pallets, part 2: columns that are ALREADY numeric but too
-- narrow. The loop above only matches integer types, so these two were
-- silently skipped and would keep scale 2, rounding away the 4th
-- decimal place the capture API writes.
--
-- numeric(10,2) -> numeric(14,4) widens BOTH the integer part
-- (10-2 = 8 digits -> 14-4 = 10 digits) and the scale (2 -> 4), so the
-- conversion cannot round or overflow any stored value. The guard
-- below proves that against the live data before converting rather
-- than assuming it: it checks total significant digits and scale
-- separately, not MAX() alone.
-- ----------------------------------------------------------

DO $$
DECLARE
    target record;
    bad_count bigint;
BEGIN
    FOR target IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns AS c
        WHERE c.table_schema = 'public'
          AND c.data_type = 'numeric'
          AND (c.table_name, c.column_name) IN (
              VALUES
                  ('hourly_updates', 'expected_pallets'),
                  ('hourly_updates', 'estimated_lost_minutes')
          )
          -- Only act while the column is genuinely narrower than the
          -- target; re-running after a successful apply is a no-op.
          AND (c.numeric_precision IS NULL
               OR c.numeric_scale IS NULL
               OR c.numeric_precision < 14
               OR c.numeric_scale < 4)
    LOOP
        -- Refuse to convert if ANY row would not fit numeric(14,4):
        --   * more than 10 digits left of the point, or
        --   * more than 4 digits of scale.
        EXECUTE format(
            'SELECT count(*) FROM public.%I WHERE %I IS NOT NULL AND ('
            || ' trunc(abs(%I)) >= 10^10 OR scale(%I) > 4 )',
            target.table_name, target.column_name,
            target.column_name, target.column_name
        ) INTO bad_count;

        IF bad_count > 0 THEN
            RAISE EXCEPTION
                'ABORT: %.% has % row(s) that do not fit numeric(14,4). '
                'Nothing has been changed - investigate before re-running.',
                target.table_name, target.column_name, bad_count;
        END IF;

        RAISE NOTICE 'Widening %.% (numeric) to numeric(14,4)',
            target.table_name, target.column_name;
        EXECUTE format(
            'ALTER TABLE public.%I ALTER COLUMN %I TYPE numeric(14,4) USING %I::numeric(14,4)',
            target.table_name, target.column_name, target.column_name
        );
    END LOOP;
END
$$;

-- React HMI hourly updates do not capture reported OEE.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'hourly_updates'
          AND column_name = 'oee'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE public.hourly_updates ALTER COLUMN oee DROP NOT NULL;
    END IF;
END
$$;

-- ----------------------------------------------------------
-- 3. downtime_events
-- ----------------------------------------------------------
-- machine_id / button_id link a React HMI fault report to the
-- configured machine/button (migration 0001) while the existing free
-- text `machine` column keeps holding the name, so CLI rows and every
-- existing query keep working. maintenance_preventable is set only
-- when an engineer closes the fault; NULL means "not recorded"
-- (every historical fault) and is never inferred from notes.

ALTER TABLE public.downtime_events
    ADD COLUMN machine_id bigint NULL REFERENCES public.machines (id),
    ADD COLUMN button_id bigint NULL REFERENCES public.buttons (id),
    ADD COLUMN reported_via text NULL
        CONSTRAINT chk_downtime_events_reported_via
            CHECK (reported_via IN ('cli', 'react_hmi')),
    ADD COLUMN report_note text NULL,
    ADD COLUMN maintenance_preventable text NULL
        CONSTRAINT chk_downtime_events_maintenance_preventable
            CHECK (maintenance_preventable IN ('Yes', 'No', 'Unsure'));

-- idx_downtime_events_production_run_id is NOT created here: it already
-- exists live with exactly the required definition
--   CREATE INDEX ... ON public.downtime_events USING btree (production_run_id)
-- and is listed in the PREFLIGHT as a REQUIRED EXISTING object.

CREATE INDEX idx_downtime_events_opened_at
    ON public.downtime_events USING btree (opened_at);

-- ----------------------------------------------------------
-- 4. planned_downtime_events
-- ----------------------------------------------------------
-- A real start/end interval per planned stop, so attribution can clip
-- it to the reporting window and never double-count it.

CREATE TABLE public.planned_downtime_events (
    id                  bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    production_run_id   bigint NOT NULL REFERENCES public.production_runs (id),
    production_line     text NOT NULL,
    reason              text NOT NULL,
    started_by          text NOT NULL,
    started_at          timestamptz NOT NULL,
    ended_by            text NULL,
    ended_at            timestamptz NULL,
    duration_minutes    numeric(14,4) NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_planned_downtime_end_after_start
        CHECK (ended_at IS NULL OR ended_at >= started_at),
    CONSTRAINT chk_planned_downtime_duration_non_negative
        CHECK (duration_minutes IS NULL OR duration_minutes >= 0)
);

-- At most one open planned stop per run.
CREATE UNIQUE INDEX uq_planned_downtime_one_open_per_run
    ON public.planned_downtime_events (production_run_id)
    WHERE ended_at IS NULL;

CREATE INDEX idx_planned_downtime_started_at
    ON public.planned_downtime_events USING btree (started_at);

-- ----------------------------------------------------------
-- 5. production_run_xray_counts
-- ----------------------------------------------------------
-- One row per end-of-shift or run-completion X-ray capture. The
-- palletised figure is snapshotted from the hourly updates the capture
-- covers (ids after the previous capture's covered_to_hourly_update_id,
-- up to and including this row's), so every waste estimate is
-- auditable.

CREATE TABLE public.production_run_xray_counts (
    id                              bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    production_run_id               bigint NOT NULL REFERENCES public.production_runs (id),
    production_line                 text NOT NULL,
    capture_point                   text NOT NULL,
    shift                           text NOT NULL,
    shift_window_start              timestamptz NOT NULL,
    line_technician                 text NOT NULL,
    count_available                 boolean NOT NULL,
    xray_pack_count                 bigint NULL,
    unavailable_reason              text NULL,
    covered_to_hourly_update_id     bigint NULL,
    palletised_pallets              numeric(14,4) NOT NULL,
    palletised_packs                numeric(14,4) NOT NULL,
    post_xray_pack_difference       numeric(14,4) NULL,
    estimated_waste_percent         numeric(9,4) NULL,
    waste_status                    text NOT NULL,
    captured_at                     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_xray_capture_point
        CHECK (capture_point IN ('shift_end', 'run_completion')),
    CONSTRAINT chk_xray_count_non_negative
        CHECK (xray_pack_count IS NULL OR xray_pack_count >= 0),
    CONSTRAINT chk_xray_available_or_reason
        CHECK (
            (count_available AND xray_pack_count IS NOT NULL AND unavailable_reason IS NULL)
            OR (NOT count_available AND xray_pack_count IS NULL
                AND unavailable_reason IS NOT NULL AND length(btrim(unavailable_reason)) > 0)
        ),
    CONSTRAINT chk_xray_waste_status
        CHECK (waste_status IN ('estimated', 'unavailable', 'data_quality_warning', 'no_output')),
    CONSTRAINT chk_xray_waste_only_when_available
        CHECK (count_available OR (post_xray_pack_difference IS NULL AND estimated_waste_percent IS NULL))
);

CREATE UNIQUE INDEX uq_xray_one_run_completion_per_run
    ON public.production_run_xray_counts (production_run_id)
    WHERE capture_point = 'run_completion';

CREATE UNIQUE INDEX uq_xray_one_shift_end_per_run_shift
    ON public.production_run_xray_counts (production_run_id, shift_window_start)
    WHERE capture_point = 'shift_end';

CREATE INDEX idx_xray_captured_at
    ON public.production_run_xray_counts USING btree (captured_at);

-- ----------------------------------------------------------
-- 6. changeovers
-- ----------------------------------------------------------
-- A changeover is ONE logical action paired with a planned-downtime
-- event of reason 'Changeover' on the run being changed over from.
-- Both are created in one transaction and completed in one transaction
-- (src/database.py start_run_changeover / complete_run_changeover), and
-- planned_downtime_event_id is NOT NULL and UNIQUE, so a changeover can
-- never exist without its planned stop.
-- Starts at "Start Changeover"; completes when the first ACCEPTABLE
-- packs of the new run are produced (not when machines restart).
-- previous_* are snapshotted from the run at start; new_* are entered
-- by the technician at start.

CREATE TABLE public.changeovers (
    id                          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    production_line             text NOT NULL,
    line_technician             text NOT NULL,
    shift                       text NOT NULL,
    status                      text NOT NULL DEFAULT 'Open',
    started_at                  timestamptz NOT NULL,
    completed_at                timestamptz NULL,
    completed_by                text NULL,
    duration_minutes            numeric(14,4) NULL,
    previous_production_run_id  bigint NOT NULL REFERENCES public.production_runs (id),
    planned_downtime_event_id   bigint NOT NULL UNIQUE REFERENCES public.planned_downtime_events (id),
    previous_customer           text NULL,
    previous_product            text NULL,
    previous_pack_weight_kg     numeric(10,3) NULL,
    previous_format             text NULL,
    new_production_run_id       bigint NULL REFERENCES public.production_runs (id),
    new_customer                text NOT NULL,
    new_product                 text NOT NULL,
    new_pack_weight_kg          numeric(10,3) NOT NULL,
    new_format                  text NOT NULL,
    note                        text NULL,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_changeover_status
        CHECK (status IN ('Open', 'Completed')),
    CONSTRAINT chk_changeover_shift
        CHECK (shift IN ('Day', 'Afternoon', 'Night')),
    CONSTRAINT chk_changeover_new_pack_weight_positive
        CHECK (new_pack_weight_kg > 0),
    CONSTRAINT chk_changeover_completion_consistent
        CHECK (
            (status = 'Open' AND completed_at IS NULL AND duration_minutes IS NULL)
            OR (status = 'Completed' AND completed_at IS NOT NULL
                AND completed_at >= started_at AND duration_minutes >= 0)
        )
);

-- At most one open changeover per production line.
CREATE UNIQUE INDEX uq_changeovers_one_open_per_line
    ON public.changeovers (production_line)
    WHERE status = 'Open';

CREATE INDEX idx_changeovers_line_started_at
    ON public.changeovers USING btree (production_line, started_at DESC);

-- ----------------------------------------------------------
-- 7. weekly_tonnage_targets
-- ----------------------------------------------------------
-- One site target and one target per line, per production week.
-- week_start is the Monday (Europe/London) the week begins; the week
-- itself runs Monday 06:00 to the following Monday 06:00 London time -
-- that boundary is computed in src/factory_time.py, not stored.

CREATE TABLE public.weekly_tonnage_targets (
    id                  bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    week_start          date NOT NULL,
    scope               text NOT NULL,
    production_line     text NULL,
    target_tonnes       numeric(12,3) NOT NULL,
    set_by              text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_weekly_target_scope
        CHECK (
            (scope = 'site' AND production_line IS NULL)
            OR (scope = 'line' AND production_line IS NOT NULL)
        ),
    CONSTRAINT chk_weekly_target_positive
        CHECK (target_tonnes > 0),
    CONSTRAINT chk_weekly_target_monday
        CHECK (EXTRACT(ISODOW FROM week_start) = 1)
);

CREATE UNIQUE INDEX uq_weekly_target_per_scope
    ON public.weekly_tonnage_targets (week_start, scope, COALESCE(production_line, ''));

-- ----------------------------------------------------------
-- 8. hmi_idempotency_keys
-- ----------------------------------------------------------
-- One row per logical HMI write. The client sends the same
-- Idempotency-Key until the action succeeds or is cancelled. The row is
-- INSERTed first inside the write's own transaction (a concurrent
-- duplicate blocks on the primary key until the first commits or rolls
-- back), and the response is stored before COMMIT - so the key, the
-- business rows and the stored response always land together or not
-- at all. A repeat with the same key and the same request replays the
-- stored response; the same key with a different request is a 409.

-- RETENTION: 90 days. created_at and expires_at are both set by the
-- database DEFAULT and are never sent by the HMI, so a client cannot
-- shorten its own duplicate protection by claiming an early expiry.
-- This migration removes no rows, and no HMI write removes rows either;
-- deleting expired keys is a separate maintenance operation
-- (delete_expired_idempotency_keys in src/database.py). Expired rows
-- left in place are harmless - they simply keep protecting their key
-- until the sweep runs.
--
-- No extension is required, and pg_cron is deliberately NOT used: the
-- sweep is an ordinary DELETE run from outside the database, so
-- applying this migration enables nothing on its own.

CREATE TABLE public.hmi_idempotency_keys (
    idempotency_key     text PRIMARY KEY,
    action              text NOT NULL,
    request_fingerprint text NOT NULL,
    production_run_id   bigint NULL REFERENCES public.production_runs (id),
    response_status     integer NULL,
    response_body       jsonb NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
    CONSTRAINT chk_idempotency_key_format
        CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{16,100}$'),
    -- A key can never expire before it was created, whatever any future
    -- caller supplies.
    CONSTRAINT chk_idempotency_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_hmi_idempotency_keys_created_at
    ON public.hmi_idempotency_keys USING btree (created_at);

-- Supports the retention sweep (WHERE expires_at <= now()) and the
-- expired-key takeover check performed when a key is claimed.
CREATE INDEX idx_hmi_idempotency_keys_expires_at
    ON public.hmi_idempotency_keys USING btree (expires_at);

-- ----------------------------------------------------------
-- 9. Security for the five new tables
-- ----------------------------------------------------------
-- Only the FastAPI backend touches these tables, over its own trusted
-- database connection. No browser and no PostgREST client may reach
-- them, so each one gets:
--
--   * ROW LEVEL SECURITY enabled with NO policies. In PostgreSQL that
--     is deny-all for every non-owner, non-BYPASSRLS role. Enabling RLS
--     without a policy is the point, not an oversight - a permissive
--     `authenticated` policy is deliberately NOT added.
--   * ALL PRIVILEGES revoked from anon and authenticated, so the Data
--     API cannot read, write, reference, trigger or truncate them even
--     if RLS were later disabled by accident. Two independent layers.
--   * PUBLIC revoked as well, so no privilege arrives via the implicit
--     PUBLIC grant or a future default-privilege change.
--
-- The identity sequences belong to the tables (GENERATED ... AS
-- IDENTITY), but their USAGE/SELECT/UPDATE privileges are revoked
-- explicitly too: a sequence is a separate object and does not inherit
-- the table's grants.
--
-- This block does NOT touch the grants on any pre-existing table - see
-- the FOLLOW-UP note in the header about the TRUNCATE grants.

ALTER TABLE public.planned_downtime_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.production_run_xray_counts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.changeovers                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.weekly_tonnage_targets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hmi_idempotency_keys         ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE
    public.planned_downtime_events,
    public.production_run_xray_counts,
    public.changeovers,
    public.weekly_tonnage_targets,
    public.hmi_idempotency_keys
FROM anon, authenticated, PUBLIC;

-- Identity sequences created by the four bigint IDENTITY columns.
-- hmi_idempotency_keys has a text primary key and no sequence.
DO $$
DECLARE
    seq record;
BEGIN
    FOR seq IN
        SELECT s.relname AS sequence_name
        FROM pg_class AS s
        JOIN pg_namespace AS n ON n.oid = s.relnamespace
        JOIN pg_depend AS d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
        JOIN pg_class AS t ON t.oid = d.refobjid
        WHERE s.relkind = 'S'
          AND n.nspname = 'public'
          AND t.relname IN (
              'planned_downtime_events', 'production_run_xray_counts',
              'changeovers', 'weekly_tonnage_targets'
          )
    LOOP
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM anon, authenticated, PUBLIC',
            seq.sequence_name
        );
        RAISE NOTICE 'Revoked sequence privileges on public.%', seq.sequence_name;
    END LOOP;
END
$$;

COMMIT;
