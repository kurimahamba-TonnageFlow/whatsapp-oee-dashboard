-- Rovema Casepacker fault presets, exact wording confirmed by the user.
-- Configuration only. Apply machine_dropdowns.sql first. Dry run by default.
-- psql -X -v applied_by="Name" [-v commit=true] -d "$DATABASE_URL" -f rovema_casepacker_presets.sql
-- Existing machine IDs, buttons and fault history are not renamed or moved.
\set ON_ERROR_STOP on
\if :{?applied_by}
\else
  \echo 'Pass -v applied_by="Your Name" for the audit log.'
  \quit
\endif
\if :{?commit}
\else
  \set commit false
\endif
BEGIN;
LOCK TABLE public.machines IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.buttons IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE desired_casepacker_buttons(machine text, reason text, ordering integer) ON COMMIT DROP;
INSERT INTO desired_casepacker_buttons VALUES
 ('Casepacker','Magazine pull error',1),
 ('Casepacker','Product positioning',2),
 ('Casepacker','Infeed jam',3),
 ('Casepacker','Cycle-chain overload',4),
 ('Casepacker','Main discharge conveyor',5),
 ('Casepacker','Pusher limit position',6),
 ('Casepacker','Gluing issues',7),
 ('Casepacker','Printer',8),
 ('Casepacker','Purge printer',9);
DO $$
BEGIN
 IF (SELECT count(*) FROM public.machines m JOIN public.production_lines p ON p.id=m.production_line_id
     WHERE p.name='Rovema' AND p.active AND m.active AND m.name IN (SELECT machine FROM desired_casepacker_buttons)) <> 1 THEN
  RAISE EXCEPTION 'Configure the active Rovema Casepacker record first.';
 END IF;
 IF EXISTS (SELECT 1 FROM public.buttons b JOIN public.machines m ON m.id=b.machine_id
            JOIN public.production_lines p ON p.id=m.production_line_id
            JOIN desired_casepacker_buttons d ON d.machine=m.name AND d.reason=b.name
            WHERE p.name='Rovema' AND (b.event_type<>'unplanned_fault' OR NOT b.active)) THEN
  RAISE EXCEPTION 'An existing inactive or differently classified preset needs review. No changes applied.';
 END IF;
END $$;
WITH added AS (
 INSERT INTO public.buttons(machine_id,name,event_type,ownership,display_order)
 SELECT m.id,d.reason,'unplanned_fault','Production',d.ordering
 FROM desired_casepacker_buttons d JOIN public.machines m ON m.name=d.machine
 JOIN public.production_lines p ON p.id=m.production_line_id AND p.name='Rovema'
 WHERE NOT EXISTS (SELECT 1 FROM public.buttons b WHERE b.machine_id=m.id AND b.name=d.reason)
 RETURNING *
)
INSERT INTO public.management_audit_log(action,manager_name,record_type,record_id,new_value,reason)
SELECT 'create_button', :'applied_by','button',id::text,to_jsonb(added),
 'User-confirmed Rovema Casepacker fault presets' FROM added;
SELECT m.name AS equipment,b.name AS fault
FROM public.buttons b JOIN public.machines m ON m.id=b.machine_id
JOIN public.production_lines p ON p.id=m.production_line_id
WHERE p.name='Rovema' AND m.name IN (SELECT machine FROM desired_casepacker_buttons) AND b.active
ORDER BY m.display_order,b.display_order,b.id;
\if :commit
 COMMIT;
\else
 ROLLBACK;
 \echo 'DRY RUN: nothing saved.'
\endif
