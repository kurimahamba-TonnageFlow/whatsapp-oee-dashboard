-- Extend existing single-factory weekly targets; preserve prior weeks and RLS.
BEGIN;
ALTER TABLE public.weekly_tonnage_targets ADD COLUMN notes text NOT NULL DEFAULT '' CHECK (length(notes)<=500);
ALTER TABLE public.weekly_tonnage_targets DROP CONSTRAINT chk_weekly_target_monday;
ALTER TABLE public.weekly_tonnage_targets ADD CONSTRAINT chk_line_target_monday CHECK (scope='site' OR EXTRACT(ISODOW FROM week_start)=1);
ALTER TABLE public.weekly_tonnage_targets ADD CONSTRAINT no_overlapping_site_target_weeks EXCLUDE USING gist (daterange(week_start,week_start+7,'[)') WITH &&) WHERE (scope='site');
ALTER TABLE public.weekly_tonnage_targets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.weekly_tonnage_targets FROM PUBLIC, anon, authenticated;
COMMIT;
