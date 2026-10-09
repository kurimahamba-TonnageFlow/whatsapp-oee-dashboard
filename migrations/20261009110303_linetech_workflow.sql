-- Additive, backend-only LineTech configuration and changeover evidence.
BEGIN;
ALTER TABLE public.production_lines ADD COLUMN linetech_config jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.planned_downtime_events ADD COLUMN component text;
ALTER TABLE public.changeovers ADD COLUMN workflow jsonb;
ALTER TABLE public.downtime_events ADD COLUMN linetech_resolved_at timestamptz;
ALTER TABLE public.casepacker_requests ADD COLUMN cancelled_at timestamptz;
ALTER TABLE public.casepacker_requests ADD COLUMN first_accepted_at timestamptz;
UPDATE public.casepacker_requests q SET first_accepted_at = COALESCE(
 (SELECT min(u.created_at) FROM public.casepacker_updates u WHERE u.request_id=q.id AND u.action='accept'), q.accepted_at);
ALTER TABLE public.production_lines ADD CONSTRAINT linetech_config_object CHECK (jsonb_typeof(linetech_config)='object');
ALTER TABLE public.changeovers ADD CONSTRAINT linetech_workflow_object CHECK (workflow IS NULL OR jsonb_typeof(workflow)='object');

CREATE OR REPLACE FUNCTION public.guard_casepacker_run_start() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE c record;
BEGIN
 IF NEW.status = 'Active' THEN
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.production_line, 0));
  IF EXISTS (SELECT 1 FROM public.casepacker_requests q JOIN public.line_stoppages s ON s.id=q.line_stoppage_id
             WHERE s.production_line=NEW.production_line AND s.ended_at IS NULL AND q.ready_at IS NULL AND q.cancelled_at IS NULL) THEN
   RAISE EXCEPTION 'Engineering must complete the changeover work before starting a run.'
    USING ERRCODE='23514', CONSTRAINT='casepacker_ready_before_run';
  END IF;
  SELECT ch.*, s.physical_ended_at INTO c FROM public.changeovers ch
   JOIN public.line_stoppages s ON s.id=ch.line_stoppage_id
   WHERE s.production_line=NEW.production_line AND s.ended_at IS NULL AND ch.workflow IS NOT NULL;
  IF FOUND AND c.workflow->>'cancelled_at' IS NULL THEN
   IF c.physical_ended_at IS NULL OR c.workflow->>'qa_status' IS DISTINCT FROM 'verified' THEN
    RAISE EXCEPTION 'Complete physical work and record changeover verification before restart.'
     USING ERRCODE='23514', CONSTRAINT='linetech_ready_before_run';
   END IF;
   IF (c.workflow->>'kind'='product' AND NEW.product IS DISTINCT FROM c.workflow->>'next_value')
    OR (c.workflow->>'kind'='format' AND NEW.format IS DISTINCT FROM c.workflow->>'next_value')
    OR (c.workflow->>'kind'='size' AND NEW.pack_weight_kg IS DISTINCT FROM (c.workflow->>'next_value')::numeric) THEN
    RAISE EXCEPTION 'New run configuration does not match the confirmed changeover.'
     USING ERRCODE='23514', CONSTRAINT='linetech_configuration_match';
   END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
-- Existing tables remain behind their current RLS and backend-only access.
REVOKE ALL ON FUNCTION public.guard_casepacker_run_start() FROM PUBLIC, anon, authenticated;
COMMIT;
