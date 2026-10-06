-- Apply after 20261002234341_casepacker_readiness.sql.
BEGIN;
ALTER TABLE public.casepacker_updates DROP CONSTRAINT casepacker_updates_action_check;
ALTER TABLE public.casepacker_updates ADD CONSTRAINT casepacker_updates_action_check
 CHECK (action IN ('accept','update','ready','handover'));
ALTER TABLE public.casepacker_updates ADD CONSTRAINT casepacker_handover_note_required
 CHECK (action <> 'handover' OR length(btrim(note)) > 0);
COMMIT;
