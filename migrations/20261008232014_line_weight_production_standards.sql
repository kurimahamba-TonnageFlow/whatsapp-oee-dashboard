-- New standards apply by line and weight. Existing versions and run snapshots
-- are retained unchanged. Newest effective applicable version wins.
BEGIN;
ALTER TABLE public.production_standard_versions
 ALTER COLUMN product DROP NOT NULL,
 ALTER COLUMN pack_type DROP NOT NULL,
 ALTER COLUMN packs_per_case DROP NOT NULL,
 ALTER COLUMN cases_per_pallet DROP NOT NULL;
ALTER TABLE public.production_standard_versions ADD CONSTRAINT standard_scope_complete
 CHECK ((product IS NULL AND pack_type IS NULL AND packs_per_case IS NULL AND cases_per_pallet IS NULL)
 OR (product IS NOT NULL AND pack_type IS NOT NULL AND packs_per_case IS NOT NULL AND cases_per_pallet IS NOT NULL));
CREATE INDEX production_standard_line_weight ON public.production_standard_versions
 (production_line, pack_weight_kg, effective_at DESC, id DESC);
CREATE FUNCTION public.resolve_production_standard(
 line_name text, weight numeric, product_name text, format_name text,
 case_packs integer, pallet_cases integer, at_time timestamptz)
RETURNS SETOF public.production_standard_versions
LANGUAGE sql STABLE SET search_path=public AS $$
 SELECT v.* FROM public.production_standard_versions v
 WHERE v.production_line=line_name AND v.pack_weight_kg=weight
 AND v.effective_at<=at_time
 AND (v.product IS NULL OR (
 public.canonical_product(v.product)=public.canonical_product(product_name)
 AND lower(trim(v.pack_type))=lower(trim(format_name))
 AND v.packs_per_case=case_packs AND v.cases_per_pallet=pallet_cases))
 ORDER BY v.effective_at DESC, v.id DESC LIMIT 1
$$;
REVOKE ALL ON FUNCTION public.resolve_production_standard(text,numeric,text,text,integer,integer,timestamptz)
 FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE FUNCTION public.select_run_standard() RETURNS trigger
LANGUAGE plpgsql SET search_path=public AS $$
DECLARE version public.production_standard_versions%ROWTYPE;
BEGIN
 SELECT * INTO version FROM public.resolve_production_standard(
 NEW.production_line, NEW.pack_weight_kg, NEW.product, NEW.pack_type,
 NEW.packs_per_case, NEW.cases_per_pallet, NEW.started_at);
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Management must configure a standard for this line and pack weight'
   USING ERRCODE='23514', CONSTRAINT='management_standard_required';
 END IF;
 NEW.standard_version_id := version.id;
 NEW.standard_speed_ppm := version.standard_speed_ppm;
 NEW.target_speed_ppm := version.standard_speed_ppm;
 RETURN NEW;
END $$;
COMMIT;
