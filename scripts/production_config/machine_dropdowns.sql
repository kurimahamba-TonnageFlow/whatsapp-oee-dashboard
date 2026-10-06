-- ==========================================================
-- TONNAGEFLOW PULSE
-- Production configuration: HMI machine dropdowns per line
-- ==========================================================
--
-- Sets the machines the HMI "Report to Engineer" dropdown offers on each
-- selected line to the confirmed list (30 Sep 2026), in this order. Configuration
-- only - no schema change, safe to run again (a second run changes
-- nothing and writes no audit rows).
--
-- History is never changed:
--   - nothing is deleted and nothing is renamed;
--   - a machine whose exact name is on the list is kept (reactivated and
--     re-ordered if needed), so faults already linked to it stay linked;
--   - any other active machine on the selected line is set active = false.
--     Old faults keep their machine_id and the machine name captured when
--     they were reported; an inactive machine simply stops appearing in
--     the dropdown (the server also refuses new reports against it);
--   - every change is written to management_audit_log (before/after).
--
-- Rovema only by default (MVP). A later line requires an explicit -v target_line.
-- Fault buttons are never moved or renamed. Refuse to hide a machine with
-- active preset buttons until its mapping has been reviewed and configured.
--
-- RUN (PostgreSQL 17 psql; take and verify a backup first):
--   Defaults to Rovema. Optional future scope: -v target_line="Guill" or "GIC".
--   A single invocation can change only one line.
--   Dry run - shows the result, then rolls everything back:
--     psql -X -v applied_by="Your Name" -d "$DATABASE_URL" -f machine_dropdowns.sql
--   Apply:
--     psql -X -v applied_by="Your Name" -v commit=true -d "$DATABASE_URL" -f machine_dropdowns.sql
--
-- Stops at the first error and rolls back (nothing half-applied). It also
-- rolls back if the final check does not find exactly the list below.

\set ON_ERROR_STOP on
\if :{?target_line}
\else
    \set target_line Rovema
\endif
\if :{?applied_by}
\else
    \echo 'Refusing to run: pass -v applied_by="Your Name" (recorded in the audit log).'
    \quit
\endif
\if :{?commit}
\else
    \set commit false
\endif

-- The names contain an em dash and '&': send them as UTF-8 whatever the
-- terminal's code page.
SET client_encoding = 'UTF8';

BEGIN;

CREATE TEMP TABLE desired_machines (
    line_name     text NOT NULL,
    machine_name  text NOT NULL,
    display_order integer NOT NULL,
    PRIMARY KEY (line_name, machine_name)
) ON COMMIT DROP;

INSERT INTO desired_machines (line_name, machine_name, display_order) VALUES
    ('Rovema', 'SBS Bagger BV1',                        1),
    ('Rovema', 'SBS Bagger BV2',                        2),
    ('Rovema', 'SBS Shared Equipment',                 3),
    ('Rovema', 'X-ray / Checkweigher',                  4),
    ('Rovema', 'Casepacker',                            5),
    ('Rovema', 'Robot Palletiser',                      6),
    ('Guill',  'Bagger — Primary & Secondary Folding',  1),
    ('Guill',  'X-ray / Checkweigher',                  2),
    ('Guill',  'Lazy Susan',                            3),
    ('Guill',  'Box Taper',                             4),
    ('GIC',    'Bagger',                                1),
    ('GIC',    'X-ray / Checkweigher',                  2),
    ('GIC',    'Lazy Susan',                            3),
    ('GIC',    'Box Taper',                             4);

-- Scope the desired list before any persistent writes. Unknown input is
-- rejected, never interpreted as "all lines".
DELETE FROM desired_machines WHERE line_name <> :'target_line';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM desired_machines) THEN
        RAISE EXCEPTION 'Unknown target_line. Choose Rovema, Guill or GIC.';
    END IF;
    IF (SELECT count(*) FROM public.production_lines
        WHERE name IN (SELECT DISTINCT line_name FROM desired_machines) AND active) <> 1 THEN
        RAISE EXCEPTION 'Expected the selected production line to exist and be active.';
    END IF;
END
$$;

-- Serialise with any other configuration change while this runs.
LOCK TABLE public.machines IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.buttons IN SHARE ROW EXCLUSIVE MODE;

-- Avoid silently making the technician's current preset buttons disappear.
DO $$
DECLARE affected text;
BEGIN
    SELECT string_agg(DISTINCT m.name, ', ' ORDER BY m.name) INTO affected
    FROM public.machines m
    JOIN public.production_lines pl ON pl.id=m.production_line_id
    JOIN public.buttons b ON b.machine_id=m.id AND b.active
    WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines)
      AND m.active
      AND NOT EXISTS (SELECT 1 FROM desired_machines d
                      WHERE d.line_name=pl.name AND d.machine_name=m.name);
    IF affected IS NOT NULL THEN
        RAISE EXCEPTION 'Preset mapping review required: active buttons on machines that would be hidden: %. No changes applied.', affected;
    END IF;
END
$$;


CREATE TEMP TABLE machines_before ON COMMIT DROP AS
SELECT m.*
FROM public.machines AS m
JOIN public.production_lines AS pl ON pl.id = m.production_line_id
WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines);

-- 1. Add missing machines; reactivate / re-order ones with an exact name.
INSERT INTO public.machines (production_line_id, name, active, display_order)
SELECT pl.id, d.machine_name, true, d.display_order
FROM desired_machines AS d
JOIN public.production_lines AS pl ON pl.name = d.line_name
ON CONFLICT (production_line_id, name) DO UPDATE
    SET active = true,
        display_order = EXCLUDED.display_order,
        updated_at = now()
    WHERE public.machines.active IS DISTINCT FROM true
       OR public.machines.display_order IS DISTINCT FROM EXCLUDED.display_order;

-- 2. Hide every other active machine on the selected line (never deleted).
UPDATE public.machines AS m
SET active = false,
    updated_at = now()
FROM public.production_lines AS pl
WHERE pl.id = m.production_line_id
  AND pl.name IN (SELECT DISTINCT line_name FROM desired_machines)
  AND m.active
  AND NOT EXISTS (
      SELECT 1 FROM desired_machines AS d
      WHERE d.line_name = pl.name AND d.machine_name = m.name
  );

-- 3. Audit every row that changed, in the Management API's format.
INSERT INTO public.management_audit_log
    (action, manager_name, record_type, record_id, previous_value, new_value, reason)
SELECT
    CASE WHEN b.id IS NULL THEN 'create_machine' ELSE 'update_machine' END,
    :'applied_by',
    'machine',
    a.id::text,
    CASE WHEN b.id IS NULL THEN NULL
         ELSE jsonb_build_object('id', b.id, 'production_line_id', b.production_line_id, 'name', b.name,
                                 'active', b.active, 'display_order', b.display_order) END,
    jsonb_build_object('id', a.id, 'production_line_id', a.production_line_id, 'name', a.name,
                       'active', a.active, 'display_order', a.display_order),
    'Confirmed HMI machine dropdown mapping (scripts/production_config/machine_dropdowns.sql)'
FROM public.machines AS a
JOIN public.production_lines AS pl ON pl.id = a.production_line_id
LEFT JOIN machines_before AS b ON b.id = a.id
WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines)
  AND (b.id IS NULL
       OR b.active IS DISTINCT FROM a.active
       OR b.display_order IS DISTINCT FROM a.display_order);

-- 4. The active list must now be exactly the confirmed one.
DO $$
DECLARE
    mismatches integer;
BEGIN
    SELECT count(*) INTO mismatches FROM (
        (SELECT pl.name, m.name, m.display_order
         FROM public.machines AS m
         JOIN public.production_lines AS pl ON pl.id = m.production_line_id
         WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines) AND m.active
         EXCEPT
         SELECT line_name, machine_name, display_order FROM desired_machines)
        UNION ALL
        (SELECT line_name, machine_name, display_order FROM desired_machines
         EXCEPT
         SELECT pl.name, m.name, m.display_order
         FROM public.machines AS m
         JOIN public.production_lines AS pl ON pl.id = m.production_line_id
         WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines) AND m.active)
    ) AS diff;
    IF mismatches <> 0 THEN
        RAISE EXCEPTION 'Active machines do not match the confirmed list (% differences).', mismatches;
    END IF;
END
$$;

\echo 'Active machines per line after this run:'
SELECT pl.name AS line, m.display_order AS "order", m.name AS machine, m.id
FROM public.machines AS m
JOIN public.production_lines AS pl ON pl.id = m.production_line_id
WHERE pl.name IN (SELECT DISTINCT line_name FROM desired_machines) AND m.active
ORDER BY pl.display_order, m.display_order;

\echo 'Changes made by this run (audit rows):'
SELECT action, record_id, new_value ->> 'name' AS machine, new_value ->> 'active' AS active,
       new_value ->> 'display_order' AS "order"
FROM public.management_audit_log
WHERE created_at = now() AND record_type = 'machine'
ORDER BY id;

\if :commit
    COMMIT;
    \echo 'COMMITTED.'
\else
    ROLLBACK;
    \echo 'DRY RUN - rolled back, nothing changed. Re-run with -v commit=true to apply.'
\endif
