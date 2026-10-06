-- ==========================================================
-- TONNAGEFLOW PULSE
-- Migration 0004: fixed-hour reporting, End Run / handover,
-- line stoppages, carried-fault acknowledgement, target-speed changes
-- ==========================================================
--
-- NOT APPLIED. Written for review; apply only after the preflight
-- below, a verified backup, and Kuri's go-ahead.
--
-- Adds what the agreed run and hourly workflow needs:
--   1. hourly_updates.hour_start - each React HMI reading is for one
--      named factory clock hour (e.g. 06:00-07:00), at most one reading
--      per run per hour.
--   2. run_target_speed_changes - a mid-run target speed change with
--      its reason, who made it and when it took effect (forward only).
--   3. line_stoppages - what happened BETWEEN product runs (Handover,
--      Changeover, Other, Restart delay, Not scheduled), attached to the
--      line, not to either run; line_stoppage_reclassifications - the
--      audit trail of every manager correction to one.
--   4. changeovers - may now be recorded against a line stoppage (the
--      new End Run -> Changeover flow) instead of an in-run planned
--      stop; the new product is filled in when the new run starts.
--   5. downtime_events escalation fields + fault_acknowledgements - an
--      incoming technician acknowledges and escalates each fault still
--      open on the line. Escalation UPDATES the existing fault; it
--      never creates another fault row.
--   6. run_next_step_legacy_baseline - every run that had ALREADY ENDED
--      when this migration runs is marked "legacy resolved": it never
--      asks for an End Run next-step choice, blocks no Start Run and gets
--      no line stoppage. Runs that end after this migration still need a
--      choice. See section 7.
--
-- ADDITIVE ONLY:
--   - Every column added to an existing table is nullable. No existing
--     row is updated, deleted or backfilled. Legacy hourly updates keep
--     hour_start NULL and read back exactly as before.
--   - The ONLY rows written are the legacy-baseline markers (section 7),
--     into the new run_next_step_legacy_baseline table. No line stoppage,
--     downtime or changeover row is created for any historical run.
--   - Relaxing NOT NULL on four changeovers columns and on
--     changeovers.planned_downtime_event_id accepts MORE rows, never
--     fewer; every existing row stays valid. The legacy in-run flow's
--     invariant (a planned stop AND the full new configuration) is
--     re-stated as a CHECK so it still holds for those rows.
--
-- PREFLIGHT (read-only; run first, expect the stated results):
--   SELECT to_regclass('public.run_target_speed_changes');   -- NULL
--   SELECT to_regclass('public.line_stoppages');             -- NULL
--   SELECT to_regclass('public.fault_acknowledgements');     -- NULL
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema = 'public'
--      AND ((table_name = 'hourly_updates' AND column_name = 'hour_start')
--        OR (table_name = 'changeovers' AND column_name = 'line_stoppage_id')
--        OR (table_name = 'downtime_events'
--            AND column_name IN ('escalation_count', 'last_escalated_at',
--                                'last_escalated_by')));  -- 0 rows
--   SELECT to_regclass('public.changeovers');                -- not NULL (0003)
--   SELECT to_regclass('public.planned_downtime_events');    -- not NULL (0003)
--   SELECT to_regclass('public.line_stoppage_reclassifications'); -- NULL
--   SELECT to_regclass('public.run_next_step_legacy_baseline');   -- NULL
--
-- LEGACY BASELINE PREFLIGHT (read-only; record the numbers, then compare
-- them with the count this migration NOTICEs when it runs):
--   -- columns the baseline reads (expect 4 rows: id bigint NOT NULL,
--   -- production_line text NOT NULL, status text, finished_at timestamptz):
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'production_runs'
--      AND column_name IN ('id', 'production_line', 'status', 'finished_at');
--   -- runs that will be baselined:
--   SELECT count(*) FROM public.production_runs
--    WHERE status IS DISTINCT FROM 'Active' AND finished_at IS NOT NULL;
--   -- per line: the latest ended run (the one Start Run would look at):
--   SELECT production_line, count(*), max(finished_at) FROM public.production_runs
--    WHERE status IS DISTINCT FROM 'Active' AND finished_at IS NOT NULL
--    GROUP BY production_line ORDER BY production_line;
--   -- runs still Active (NOT baselined - they will need a choice when
--   -- they end under the new workflow):
--   SELECT production_line, id, started_at FROM public.production_runs
--    WHERE status = 'Active' ORDER BY production_line;
--   -- ended without a finish time (never considered by Start Run; not
--   -- baselined; expect 0):
--   SELECT count(*) FROM public.production_runs
--    WHERE status IS DISTINCT FROM 'Active' AND finished_at IS NULL;
--
-- APPLY (after a verified backup):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0004_fixed_hour_reporting.sql
--
-- ROLLBACK (manual; only while no new-flow rows exist - these statements
-- discard their data):
--    BEGIN;
--    DROP TABLE public.run_next_step_legacy_baseline;
--    DROP TABLE public.line_stoppage_reclassifications;
--    DROP TABLE public.fault_acknowledgements;
--    ALTER TABLE public.downtime_events
--        DROP COLUMN last_escalated_by, DROP COLUMN last_escalated_at,
--        DROP COLUMN escalation_count;
--    ALTER TABLE public.changeovers
--        DROP CONSTRAINT chk_changeover_has_one_source,
--        DROP CONSTRAINT chk_changeover_in_run_has_new_configuration,
--        DROP COLUMN line_stoppage_id;
--    -- Restoring NOT NULL fails (safely) if a new-flow changeover exists:
--    ALTER TABLE public.changeovers
--        ALTER COLUMN planned_downtime_event_id SET NOT NULL,
--        ALTER COLUMN new_customer SET NOT NULL,
--        ALTER COLUMN new_product SET NOT NULL,
--        ALTER COLUMN new_pack_weight_kg SET NOT NULL,
--        ALTER COLUMN new_format SET NOT NULL;
--    DROP TABLE public.line_stoppages;
--    DROP TABLE public.run_target_speed_changes;
--    DROP INDEX public.uq_hourly_updates_one_reading_per_run_hour;
--    ALTER TABLE public.hourly_updates DROP COLUMN hour_start;
--    COMMIT;

BEGIN;

-- ----------------------------------------------------------
-- 1. hourly_updates: the named clock hour
-- ----------------------------------------------------------
-- hour_start is the UTC instant the clock hour starts. UK offsets are
-- whole hours, so it is also the London hour boundary. period_started_at
-- and period_ended_at (0003) hold the part of that hour the run was
-- open, so partial first and last hours are exact.

ALTER TABLE public.hourly_updates
    ADD COLUMN hour_start timestamptz NULL;

CREATE UNIQUE INDEX uq_hourly_updates_one_reading_per_run_hour
    ON public.hourly_updates (production_run_id, hour_start)
    WHERE hour_start IS NOT NULL;

-- ----------------------------------------------------------
-- 2. run_target_speed_changes
-- ----------------------------------------------------------
-- production_runs.target_speed_ppm always holds the CURRENT speed; the
-- starting speed is the first change's previous_speed_ppm. Each change
-- applies forward from effective_at only - earlier hours never change.

CREATE TABLE public.run_target_speed_changes (
    id                  bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    production_run_id   bigint NOT NULL REFERENCES public.production_runs (id),
    previous_speed_ppm  numeric(12,4) NOT NULL,
    new_speed_ppm       numeric(12,4) NOT NULL,
    reason              text NOT NULL,
    changed_by          text NOT NULL,
    effective_at        timestamptz NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_speed_change_positive
        CHECK (previous_speed_ppm > 0 AND new_speed_ppm > 0),
    CONSTRAINT chk_speed_change_differs
        CHECK (previous_speed_ppm <> new_speed_ppm),
    CONSTRAINT chk_speed_change_reason_present
        CHECK (length(btrim(reason)) > 0)
);

CREATE INDEX idx_run_target_speed_changes_run
    ON public.run_target_speed_changes USING btree (production_run_id, effective_at);

-- ----------------------------------------------------------
-- 3. line_stoppages
-- ----------------------------------------------------------
-- A stop BETWEEN product runs: after End Run the technician (or later a
-- manager) chooses End Shift -> handover (planned), Changeover (planned),
-- Other (unplanned, written reason required) or Not scheduled (the line
-- was not scheduled to produce: in no target and in neither planned nor
-- unplanned downtime). Resolving an Other stop starts a restart_delay
-- (unplanned, follows_stoppage_id = the Other) that the next run's start
-- ends.
-- It lowers the LINE's hourly result and is never charged to a product
-- run. previous_production_run_id is the run that just ended;
-- next_production_run_id is set when the next run starts.

CREATE TABLE public.line_stoppages (
    id                          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    production_line             text NOT NULL,
    kind                        text NOT NULL,
    reason                      text NULL,
    previous_production_run_id  bigint NULL REFERENCES public.production_runs (id),
    next_production_run_id      bigint NULL REFERENCES public.production_runs (id),
    -- The Other stop whose Resolve started this one (its Restart delay).
    -- Kept if a manager later reclassifies it, so it is never mistaken
    -- for a second next-step choice.
    follows_stoppage_id         bigint NULL REFERENCES public.line_stoppages (id),
    started_by                  text NOT NULL,
    started_at                  timestamptz NOT NULL,
    -- Changeover only: End Changeover (physical work done). The event
    -- keeps running through the new-run form until the new run starts.
    physical_ended_by           text NULL,
    physical_ended_at           timestamptz NULL,
    ended_by                    text NULL,
    ended_at                    timestamptz NULL,
    duration_minutes            numeric(14,4) NULL,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    -- handover: started_by = outgoing technician (End Shift), ended_by =
    -- incoming technician (their Start Run ends it).
    CONSTRAINT chk_line_stoppage_kind
        CHECK (kind IN ('changeover', 'other', 'handover', 'restart_delay', 'not_scheduled')),
    CONSTRAINT chk_line_stoppage_restart_delay_follows
        CHECK (kind <> 'restart_delay' OR follows_stoppage_id IS NOT NULL),
    CONSTRAINT chk_line_stoppage_physical_end
        CHECK (
            (physical_ended_at IS NULL AND physical_ended_by IS NULL)
            OR (kind = 'changeover' AND physical_ended_by IS NOT NULL
                AND physical_ended_at >= started_at
                AND (ended_at IS NULL OR physical_ended_at <= ended_at))
        ),
    CONSTRAINT chk_line_stoppage_other_has_reason
        CHECK (kind <> 'other' OR length(btrim(COALESCE(reason, ''))) > 0),
    CONSTRAINT chk_line_stoppage_end_consistent
        CHECK (
            (ended_at IS NULL AND duration_minutes IS NULL AND ended_by IS NULL)
            OR (ended_at IS NOT NULL AND ended_at >= started_at
                AND duration_minutes >= 0 AND ended_by IS NOT NULL)
        )
);

-- At most one open line stoppage per production line.
CREATE UNIQUE INDEX uq_line_stoppages_one_open_per_line
    ON public.line_stoppages (production_line)
    WHERE ended_at IS NULL;

CREATE INDEX idx_line_stoppages_line_started_at
    ON public.line_stoppages USING btree (production_line, started_at DESC);

-- One next-step choice per ended run (a stop that follows a resolved
-- Other is not a second choice). Two tablets choosing at once cannot
-- both succeed.
CREATE UNIQUE INDEX uq_line_stoppages_one_next_step_per_run
    ON public.line_stoppages (previous_production_run_id)
    WHERE previous_production_run_id IS NOT NULL AND follows_stoppage_id IS NULL;

-- At most one stop follows each Other (a repeated Resolve adds nothing).
CREATE UNIQUE INDEX uq_line_stoppages_one_follower
    ON public.line_stoppages (follows_stoppage_id)
    WHERE follows_stoppage_id IS NOT NULL;

-- ----------------------------------------------------------
-- 3b. line_stoppage_reclassifications: manager corrections
-- ----------------------------------------------------------
-- A manager may correct a stop's classification (e.g. a late "Other: No
-- orders" that was really Not scheduled). The stop stays one interval;
-- its kind/reason are updated and every change is kept here.

CREATE TABLE public.line_stoppage_reclassifications (
    id                  bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    line_stoppage_id    bigint NOT NULL REFERENCES public.line_stoppages (id),
    previous_kind       text NOT NULL,
    previous_reason     text NULL,
    new_kind            text NOT NULL,
    new_reason          text NULL,
    changed_by          text NOT NULL,
    changed_at          timestamptz NOT NULL,
    note                text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_reclassification_changes_something
        CHECK (previous_kind <> new_kind OR previous_reason IS DISTINCT FROM new_reason),
    CONSTRAINT chk_reclassification_note_present
        CHECK (length(btrim(note)) > 0)
);

CREATE INDEX idx_line_stoppage_reclassifications_stop
    ON public.line_stoppage_reclassifications USING btree (line_stoppage_id, changed_at);

-- ----------------------------------------------------------
-- 4. changeovers: recorded against a line stoppage
-- ----------------------------------------------------------

ALTER TABLE public.changeovers
    ALTER COLUMN planned_downtime_event_id DROP NOT NULL,
    ALTER COLUMN new_customer DROP NOT NULL,
    ALTER COLUMN new_product DROP NOT NULL,
    ALTER COLUMN new_pack_weight_kg DROP NOT NULL,
    ALTER COLUMN new_format DROP NOT NULL,
    ADD COLUMN line_stoppage_id bigint NULL UNIQUE REFERENCES public.line_stoppages (id);

-- Exactly one source: an in-run planned stop (legacy flow) or a line
-- stoppage (End Run -> Changeover). Every existing row has a planned
-- stop and no line stoppage, so it satisfies this.
ALTER TABLE public.changeovers
    ADD CONSTRAINT chk_changeover_has_one_source
        CHECK ((planned_downtime_event_id IS NULL) <> (line_stoppage_id IS NULL));

-- The legacy in-run flow still always records the full new configuration.
ALTER TABLE public.changeovers
    ADD CONSTRAINT chk_changeover_in_run_has_new_configuration
        CHECK (
            planned_downtime_event_id IS NULL
            OR (new_customer IS NOT NULL AND new_product IS NOT NULL
                AND new_pack_weight_kg IS NOT NULL AND new_format IS NOT NULL)
        );

-- ----------------------------------------------------------
-- 5. Carried faults: acknowledgement and escalation
-- ----------------------------------------------------------
-- escalation_count is nullable (NULL = never escalated) so no existing
-- row is rewritten; the code reads COALESCE(escalation_count, 0).

ALTER TABLE public.downtime_events
    ADD COLUMN escalation_count integer NULL,
    ADD COLUMN last_escalated_at timestamptz NULL,
    ADD COLUMN last_escalated_by text NULL;

CREATE TABLE public.fault_acknowledgements (
    id                  bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    downtime_event_id   bigint NOT NULL REFERENCES public.downtime_events (id),
    production_line     text NOT NULL,
    acknowledged_by     text NOT NULL,
    acknowledged_at     timestamptz NOT NULL,
    escalated           boolean NOT NULL,
    note                text NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fault_acknowledgements_fault
    ON public.fault_acknowledgements USING btree (downtime_event_id, acknowledged_at DESC);

-- ----------------------------------------------------------
-- 5b. run_next_step_legacy_baseline (filled in section 7)
-- ----------------------------------------------------------
-- One marker row per run that had already ended when this migration ran.
-- Its presence means "legacy resolved: no End Run next-step choice is
-- required". It is the only thing written for historical runs.

CREATE TABLE public.run_next_step_legacy_baseline (
    production_run_id   bigint PRIMARY KEY REFERENCES public.production_runs (id),
    production_line     text NOT NULL,
    run_finished_at     timestamptz NOT NULL,
    baselined_at        timestamptz NOT NULL DEFAULT now(),
    source              text NOT NULL DEFAULT 'migration 0004 legacy baseline'
);

-- ----------------------------------------------------------
-- 6. Security for the new tables (same model as 0003)
-- ----------------------------------------------------------
-- Only the FastAPI backend touches these tables. RLS enabled with NO
-- policies (deny-all for non-owner roles) plus ALL privileges revoked
-- from anon, authenticated and PUBLIC - two independent layers. The
-- identity sequences are revoked explicitly: a sequence does not
-- inherit its table's grants.

ALTER TABLE public.run_target_speed_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.line_stoppages           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fault_acknowledgements   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.line_stoppage_reclassifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.run_next_step_legacy_baseline   ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE
    public.run_target_speed_changes,
    public.line_stoppages,
    public.fault_acknowledgements,
    public.line_stoppage_reclassifications,
    public.run_next_step_legacy_baseline
FROM anon, authenticated, PUBLIC;

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
          AND t.relname IN ('run_target_speed_changes', 'line_stoppages', 'fault_acknowledgements',
                            'line_stoppage_reclassifications')
    LOOP
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM anon, authenticated, PUBLIC',
            seq.sequence_name
        );
        RAISE NOTICE 'Revoked sequence privileges on public.%', seq.sequence_name;
    END LOOP;
END
$$;

-- ----------------------------------------------------------
-- 7. Legacy baseline: runs that ended BEFORE this migration
-- ----------------------------------------------------------
-- The new workflow refuses Start Run until someone records what happened
-- after the line's last ended run, and backdates that event to the run's
-- end. Runs that ended under the old workflow never had that choice, so
-- without this every line would be blocked at go-live and the first
-- choice would create weeks of retrospective downtime.
--
-- Each already-ended run gets ONE marker row here - nothing else. No line
-- stoppage, downtime or changeover row is fabricated, and the time after
-- those runs stays exactly as it reports today (no recorded stop).
--
-- The snapshot is this statement's: a run still Active now, or one that
-- ends after this transaction commits, is NOT baselined and needs a
-- next-step choice. Idempotent (ON CONFLICT DO NOTHING) so re-running the
-- file inside a fresh transaction cannot duplicate or move a marker.

INSERT INTO public.run_next_step_legacy_baseline (production_run_id, production_line, run_finished_at)
SELECT id, production_line, finished_at
FROM public.production_runs
WHERE status IS DISTINCT FROM 'Active'
  AND finished_at IS NOT NULL
ON CONFLICT (production_run_id) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE 'Legacy baseline: % ended runs marked (no line stoppages created).',
        (SELECT count(*) FROM public.run_next_step_legacy_baseline);
END
$$;

COMMIT;
