# Management Migration — Verification Checkpoint

## Migration

`migrations/0001_management_area.sql`

## Applied

2026-09-15, approximately 02:56 UK time (BST, UTC+1). First application
— none of the four tables existed beforehand (confirmed by preflight
read-only check).

## Database environment

The Supabase/PostgreSQL database configured via `DATABASE_URL` in the
project's `.env` (credentials not shown here or anywhere in this
document).

## Tables created

`production_lines`, `machines`, `buttons`, `management_audit_log` —
all confirmed present afterward via `information_schema`, with the
exact columns, types, and nullability defined in the migration.

## Seed lines verified

`Rovema`, `GIC`, `Guill` — each exists exactly once, each `active =
true`. `production_lines` contains exactly 3 rows total: no
duplicates.

## Constraints and indexes verified

- Foreign keys: `buttons.machine_id → machines`,
  `machines.production_line_id → production_lines`.
- Check constraints: `buttons.event_type IN ('planned_downtime',
  'unplanned_fault')`, `buttons.ownership IN ('Production',
  'Engineering')`.
- Unique constraints: `production_lines.name`,
  `machines(production_line_id, name)`.
- Indexes: primary keys on all 4 tables, plus
  `idx_machines_production_line_id`, `idx_buttons_machine_id`,
  `idx_management_audit_log_created_at`,
  `idx_management_audit_log_record`.

All match the migration file exactly.

## Existing tables confirmed safe

`production_runs`, `hourly_updates`, `downtime_events`,
`engineering_updates` — row counts identical before and after
(22 / 29 / 4 / 5). The two pre-existing `Active` runs (ids 25 and 27,
both pre-existing `TEST-` marked records, untouched during this stage)
are unchanged in id, line, and status. No row was deleted, altered, or
created in any of these four tables by this migration.

## Test result

```
216 passed
```
(`test_management_api.py`, `test_runs_api.py`, `test_dashboard_api.py`,
`test_whatsapp_webhook.py`, `test_whatsapp_dom.py`,
`test_whatsapp_message_parser.py`, `test_whatsapp_message_store.py`,
`test_whatsapp_web_observer.py`)

## Warnings / remaining work

- No machines or buttons have been configured yet — `machines` and
  `buttons` are empty; `GET /api/v1/hmi/config` will currently return
  the 3 lines with no machines under them until Management adds some.
- The two pre-existing `TEST-` marked active runs (ids 25, 27) were
  deliberately left untouched this stage, per instruction.
- Management pages 1/2 and the HMI "Management" button are still not
  built — this checkpoint is backend + schema only.
