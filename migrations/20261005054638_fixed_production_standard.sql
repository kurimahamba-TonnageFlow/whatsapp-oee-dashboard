-- Additive. No historical target is asserted to be an agreed standard.
BEGIN;
ALTER TABLE public.production_runs ADD COLUMN standard_speed_ppm numeric(14,4)
  CHECK (standard_speed_ppm > 0);
CREATE TABLE public.run_operating_speed_changes (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  production_run_id bigint NOT NULL REFERENCES public.production_runs(id),
  previous_speed_ppm numeric(14,4) CHECK (previous_speed_ppm >= 0),
  new_speed_ppm numeric(14,4) NOT NULL CHECK (new_speed_ppm >= 0),
  effective_at timestamptz NOT NULL,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL CHECK (length(trim(reason)) > 0),
  changed_by text NOT NULL CHECK (length(trim(changed_by)) > 0),
  supersedes_id bigint UNIQUE REFERENCES public.run_operating_speed_changes(id)
);
CREATE INDEX run_operating_speed_timeline ON public.run_operating_speed_changes(production_run_id, effective_at, id);
ALTER TABLE public.run_operating_speed_changes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.run_operating_speed_changes FROM anon, authenticated;
-- Backend connection owns access; no client Data API policy.
CREATE FUNCTION public.protect_production_standard() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  IF NEW.standard_speed_ppm IS DISTINCT FROM OLD.standard_speed_ppm THEN
    RAISE EXCEPTION 'Run standard is immutable; historical standards require a separately reviewed backfill';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER immutable_production_standard BEFORE UPDATE ON public.production_runs
FOR EACH ROW EXECUTE FUNCTION public.protect_production_standard();
CREATE FUNCTION public.preserve_operating_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  RAISE EXCEPTION 'Operating-speed evidence is append-only; submit a correction';
END $$;
CREATE TRIGGER append_only_operating_speed BEFORE UPDATE OR DELETE ON public.run_operating_speed_changes
FOR EACH ROW EXECUTE FUNCTION public.preserve_operating_evidence();
COMMIT;
