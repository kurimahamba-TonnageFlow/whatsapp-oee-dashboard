# Engineering Migration — Verification Checkpoint

## Migration

`migrations/0002_engineering_workflow.sql`

## Purpose

Adds the columns Stage 5A's Engineering API needs for the accept /
repair-update / close workflow:

- `downtime_events.accepted_at` — when an engineer accepted a fault.
- `engineering_updates.repair_classification` (+ `CHECK` constraint
  `chk_engineering_update_repair_classification` permitting
  `'Mechanical'` or `'Machine Setting'`), `setting_name`,
  `previous_value`, `new_value`, `reason_for_change`,
  `affected_products_or_formats`, `notes`.

All eight new columns are nullable. No existing column, row, index or
constraint is dropped or altered by this migration.

An earlier draft of this migration also proposed adding
`engineering_updates.created_at`. A read-only Supabase preflight
(run before applying anything) found that column already existed live
as `timestamp with time zone, NOT NULL, DEFAULT now()`, and that the
existing `chk_engineering_update_type` CHECK constraint already
permitted the three values this API needs (`Investigation`,
`Follow Up`, `Resolution`). The migration was corrected to remove the
`created_at` statement entirely and leave `update_type` and its
constraint untouched — see `docs/engineering_integration.md` for the
full reasoning.

## Applied

18 September 2026, via the Supabase SQL Editor (exact time not
recorded in this document).

## Database environment

The Supabase/PostgreSQL database configured via `DATABASE_URL` in the
project's `.env` (credentials not shown here or anywhere in this
document).

## Verified after applying (read-only queries only)

- **All new columns present** — confirmed via `information_schema.columns`
  for all 8 columns listed above, on `downtime_events` and
  `engineering_updates` respectively.
- **`created_at` unchanged** — still `timestamp with time zone, NOT
  NULL, DEFAULT now()`, exactly as it was before this migration ran.
  Confirmed the migration added no `ADD COLUMN created_at` / `ALTER
  COLUMN created_at` statement, and the live column definition matches
  the pre-migration preflight exactly.
- **New constraint present** — `chk_engineering_update_repair_classification`
  exists on `engineering_updates`, permitting `'Mechanical'` /
  `'Machine Setting'` (NULL-permissive, so no existing row is
  rejected).
- **Original `update_type` constraint unchanged** — `chk_engineering_update_type`
  still exists, unaltered, still permitting exactly `'Investigation'`,
  `'Follow Up'`, `'Resolution'`.

## Existing rows confirmed unchanged

| | Before | After |
| --- | --- | --- |
| `downtime_events` row count | 4 | 4 |
| `engineering_updates` row count | 5 | 5 |
| `engineering_updates` rows with any new column populated | — | 0 |
| `downtime_events` rows with `accepted_at` populated | — | 0 |

`existing_updates_changed = 0` and `existing_faults_changed = 0` —
no existing row in either table was inserted, deleted, or had any
column value altered by this migration. Every new column on every
pre-existing row reads back `NULL`, as expected for a purely additive
change.

## Read-only verification method

Verification was performed exclusively with `SELECT` statements
against `information_schema` and `pg_catalog` (column definitions,
constraint definitions via `pg_get_constraintdef()`, and row counts) —
run before applying the migration (preflight) and again afterward
(post-migration check). No `ALTER`, `CREATE`, `DROP`, `INSERT`,
`UPDATE` or `DELETE` statement was used at any point during
verification. No credentials, connection strings, PINs, tokens, or
account-identifying screenshots are recorded in this document or were
used to produce it.

## Test result

```
275 passed
```
(the documented offline-safe suite — `test_management_api.py`,
`test_runs_api.py`, `test_dashboard_api.py`, the five
`test_whatsapp_*.py` files, plus the new `test_engineering_api.py`).

## Remaining work

- The Engineering React screen (Stage 5B) is not built — this
  checkpoint is backend + schema + migration only, matching Stage 5A's
  scope.
- `ENGINEERING_PIN` must be set on the deployed API process before
  `POST /api/v1/engineering/login` will work against this schema.
