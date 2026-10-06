BEGIN;
CREATE TABLE public.task_observations (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 production_line text NOT NULL CHECK (production_line = 'Rovema'),
 task text NOT NULL CHECK (task IN ('Film change','Label change','X-ray (CCP)','Casepacker','Robot Palletiser','Changeover','Format changeover')),
 technician text NOT NULL,
 started_at timestamptz NOT NULL,
 ended_at timestamptz NOT NULL CHECK (ended_at > started_at),
 product text NOT NULL,
 from_configuration text NOT NULL CHECK (length(trim(from_configuration)) > 0),
 to_configuration text NOT NULL CHECK (length(trim(to_configuration)) > 0),
 waiting_minutes numeric NOT NULL CHECK (waiting_minutes >= 0),
 shared_work boolean NOT NULL,
 completed_successfully boolean NOT NULL,
 notes text NOT NULL,
 device_name text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (waiting_minutes <= EXTRACT(EPOCH FROM (ended_at-started_at))/60),
 UNIQUE (production_line, task, technician, started_at)
);
CREATE INDEX task_observations_started ON public.task_observations(started_at DESC);
ALTER TABLE public.task_observations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.task_observations FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.task_observations_id_seq FROM PUBLIC, anon, authenticated;
CREATE FUNCTION public.preserve_task_observation() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
BEGIN RAISE EXCEPTION 'Task observations are immutable'; END $$;
CREATE TRIGGER immutable_task_observation BEFORE UPDATE OR DELETE ON public.task_observations FOR EACH ROW EXECUTE FUNCTION public.preserve_task_observation();
REVOKE ALL ON FUNCTION public.preserve_task_observation() FROM PUBLIC, anon, authenticated;
-- Match existing standard aliases without altering saved historical versions.
CREATE FUNCTION public.canonical_product(value text) RETURNS text LANGUAGE sql IMMUTABLE SET search_path=public AS $$
 SELECT CASE lower(trim(value))
 WHEN 'white bas' THEN 'white basmati' WHEN 'brown bas' THEN 'brown basmati'
 WHEN 'white lg easy cook' THEN 'white long grain easy cook'
 WHEN 'brown lg easy cook' THEN 'brown long grain easy cook'
 ELSE lower(trim(value)) END
$$;
REVOKE ALL ON FUNCTION public.canonical_product(text) FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE FUNCTION public.select_run_standard() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE version public.production_standard_versions%ROWTYPE;
BEGIN
 SELECT * INTO version FROM public.production_standard_versions
 WHERE production_line = NEW.production_line AND public.canonical_product(product) = public.canonical_product(NEW.product)
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

COMMIT;
