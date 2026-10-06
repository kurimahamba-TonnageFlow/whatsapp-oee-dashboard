-- Rovema X-ray and Robot palletiser fault presets, exact wording confirmed by the user.
-- Configuration only. Apply machine_dropdowns.sql first. Dry run by default.
-- psql -X -v applied_by="Name" [-v commit=true] -d "$DATABASE_URL" -f rovema_xray_robot_presets.sql
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
CREATE TEMP TABLE desired_xray_robot_buttons(machine text, reason text, ordering integer) ON COMMIT DROP;
INSERT INTO desired_xray_robot_buttons VALUES
 ('X-ray / Checkweigher','Machine jam',1),
 ('X-ray / Checkweigher','CCP check fail',2),
 ('Robot Palletiser','Pallet stacker fault',1),
 ('Robot Palletiser','Pallet outfeed transfer error',2),
 ('Robot Palletiser','Infeed conveyor not moving',3),
 ('Robot Palletiser','Incorrect stacking',4),
 ('Robot Palletiser','Dropping cases',5),
 ('Robot Palletiser','Safety sensor alarm',6),
 ('Robot Palletiser','Pallet position',7),
 ('Robot Palletiser','Wrapper',8);
DO $$
BEGIN
 IF (SELECT count(*) FROM public.machines m JOIN public.production_lines p ON p.id=m.production_line_id
     WHERE p.name='Rovema' AND p.active AND m.active AND m.name IN (SELECT machine FROM desired_xray_robot_buttons)) <> 2 THEN
  RAISE EXCEPTION 'Configure the active Rovema X-ray and Robot palletiser records first.';
 END IF;
 IF EXISTS (SELECT 1 FROM public.buttons b JOIN public.machines m ON m.id=b.machine_id
            JOIN public.production_lines p ON p.id=m.production_line_id
            JOIN desired_xray_robot_buttons d ON d.machine=m.name AND d.reason=b.name
            WHERE p.name='Rovema' AND (b.event_type<>'unplanned_fault' OR NOT b.active)) THEN
  RAISE EXCEPTION 'An existing inactive or differently classified preset needs review. No changes applied.';
 END IF;
END $$;
WITH added AS (
 INSERT INTO public.buttons(machine_id,name,event_type,ownership,display_order)
 SELECT m.id,d.reason,'unplanned_fault','Production',d.ordering
 FROM desired_xray_robot_buttons d JOIN public.machines m ON m.name=d.machine
 JOIN public.production_lines p ON p.id=m.production_line_id AND p.name='Rovema'
 WHERE NOT EXISTS (SELECT 1 FROM public.buttons b WHERE b.machine_id=m.id AND b.name=d.reason)
 RETURNING *
)
INSERT INTO public.management_audit_log(action,manager_name,record_type,record_id,new_value,reason)
SELECT 'create_button', :'applied_by','button',id::text,to_jsonb(added),
 'User-confirmed Rovema X-ray and Robot palletiser fault presets' FROM added;
SELECT m.name AS equipment,b.name AS fault
FROM public.buttons b JOIN public.machines m ON m.id=b.machine_id
JOIN public.production_lines p ON p.id=m.production_line_id
WHERE p.name='Rovema' AND m.name IN (SELECT machine FROM desired_xray_robot_buttons) AND b.active
ORDER BY m.display_order,b.display_order,b.id;
\if :commit
 COMMIT;
\else
 ROLLBACK;
 \echo 'DRY RUN: nothing saved.'
\endif
