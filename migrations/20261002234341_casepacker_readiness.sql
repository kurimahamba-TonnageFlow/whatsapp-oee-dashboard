-- Apply after 0004_fixed_hour_reporting.sql. Backend-only access.
BEGIN;
CREATE TABLE public.casepacker_requests (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 line_stoppage_id bigint NOT NULL UNIQUE REFERENCES public.line_stoppages(id),
 details text NOT NULL CHECK (length(btrim(details)) BETWEEN 1 AND 500),
 requested_by text NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now(),
 engineer text,
 accepted_at timestamptz,
 ready_at timestamptz,
 CHECK ((engineer IS NULL) = (accepted_at IS NULL)),
 CHECK (ready_at IS NULL OR (accepted_at IS NOT NULL AND ready_at >= accepted_at))
);
CREATE TABLE public.casepacker_updates (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 request_id bigint NOT NULL REFERENCES public.casepacker_requests(id),
 action text NOT NULL CHECK (action IN ('accept','update','ready')),
 engineer text NOT NULL,
 note text NOT NULL CHECK (length(note) <= 2000),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON public.casepacker_updates(request_id, id);
ALTER TABLE public.casepacker_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.casepacker_updates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.casepacker_requests, public.casepacker_updates FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.casepacker_requests_id_seq, public.casepacker_updates_id_seq FROM PUBLIC, anon, authenticated;
-- Serialize line start and stop creation, including when no row exists yet.
-- SECURITY INVOKER: the existing trusted backend connection performs all writes.
CREATE FUNCTION public.guard_casepacker_run_start() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
 IF NEW.status = 'Active' THEN
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.production_line, 0));
  IF EXISTS (SELECT 1 FROM public.casepacker_requests q
             JOIN public.line_stoppages s ON s.id=q.line_stoppage_id
             WHERE s.production_line=NEW.production_line AND q.ready_at IS NULL) THEN
   RAISE EXCEPTION 'Engineering must mark the casepacker ready before starting a run.'
    USING ERRCODE='23514', CONSTRAINT='casepacker_ready_before_run';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER casepacker_run_start BEFORE INSERT OR UPDATE OF status, production_line
 ON public.production_runs FOR EACH ROW EXECUTE FUNCTION public.guard_casepacker_run_start();
CREATE FUNCTION public.guard_casepacker_stop_creation() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.production_line, 0));
 IF EXISTS (SELECT 1 FROM public.production_runs WHERE production_line=NEW.production_line AND status='Active') THEN
  RAISE EXCEPTION 'End the active run before starting a line stop.' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER casepacker_stop_creation BEFORE INSERT ON public.line_stoppages
 FOR EACH ROW EXECUTE FUNCTION public.guard_casepacker_stop_creation();
REVOKE ALL ON FUNCTION public.guard_casepacker_run_start(), public.guard_casepacker_stop_creation() FROM PUBLIC, anon, authenticated;
COMMIT;
