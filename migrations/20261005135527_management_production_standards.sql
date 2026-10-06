-- Management standards are append-only. Existing run snapshots are untouched.
BEGIN;
CREATE TABLE public.production_standard_versions (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 production_line text NOT NULL,
 product text NOT NULL CHECK (length(trim(product)) > 0),
 pack_type text NOT NULL CHECK (length(trim(pack_type)) > 0),
 pack_weight_kg numeric(14,4) NOT NULL CHECK (pack_weight_kg > 0),
 packs_per_case integer NOT NULL CHECK (packs_per_case > 0),
 cases_per_pallet integer NOT NULL CHECK (cases_per_pallet > 0),
 standard_speed_ppm numeric(14,4) NOT NULL CHECK (standard_speed_ppm > 0),
 effective_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 manager_name text NOT NULL CHECK (length(trim(manager_name)) > 0),
 reason text NOT NULL CHECK (length(trim(reason)) > 0)
);
CREATE INDEX production_standard_lookup ON public.production_standard_versions
 (production_line, lower(trim(product)), lower(trim(pack_type)), pack_weight_kg,
 packs_per_case, cases_per_pallet, effective_at DESC, id DESC);
ALTER TABLE public.production_standard_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.production_standard_versions FROM anon, authenticated;
ALTER TABLE public.production_runs ADD COLUMN standard_version_id bigint
 REFERENCES public.production_standard_versions(id);
CREATE FUNCTION public.preserve_standard_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
 RAISE EXCEPTION 'Standard versions are append-only; record a new management version';
END $$;
CREATE TRIGGER immutable_standard_version BEFORE UPDATE OR DELETE ON public.production_standard_versions
 FOR EACH ROW EXECUTE FUNCTION public.preserve_standard_version();
CREATE FUNCTION public.select_run_standard() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE version public.production_standard_versions%ROWTYPE;
BEGIN
 SELECT * INTO version FROM public.production_standard_versions
 WHERE production_line = NEW.production_line AND lower(trim(product)) = lower(trim(NEW.product))
 AND lower(trim(pack_type)) = lower(trim(NEW.pack_type)) AND pack_weight_kg = NEW.pack_weight_kg
 AND packs_per_case = NEW.packs_per_case AND cases_per_pallet = NEW.cases_per_pallet
 AND effective_at <= NEW.started_at
 ORDER BY effective_at DESC, id DESC LIMIT 1;
 IF NOT FOUND THEN
   RAISE EXCEPTION 'Management must configure a standard for this line, product and pack configuration'
     USING ERRCODE = '23514', CONSTRAINT = 'management_standard_required';
 END IF;
 NEW.standard_version_id := version.id;
 NEW.standard_speed_ppm := version.standard_speed_ppm;
 NEW.target_speed_ppm := version.standard_speed_ppm;
 RETURN NEW;
END $$;
CREATE TRIGGER select_management_standard BEFORE INSERT ON public.production_runs
 FOR EACH ROW EXECUTE FUNCTION public.select_run_standard();
CREATE OR REPLACE FUNCTION public.protect_production_standard() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
 IF NEW.standard_speed_ppm IS DISTINCT FROM OLD.standard_speed_ppm
 OR NEW.standard_version_id IS DISTINCT FROM OLD.standard_version_id
 OR (OLD.standard_version_id IS NOT NULL AND NEW.target_speed_ppm IS DISTINCT FROM OLD.target_speed_ppm) THEN
   RAISE EXCEPTION 'Run standard snapshot is immutable; management changes apply to new runs only';
 END IF;
 RETURN NEW;
END $$;
COMMIT;
