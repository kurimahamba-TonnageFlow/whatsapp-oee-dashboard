# Pulse Engineering — Integration Notes

No Engineering frontend source exists in this repository yet (Stage 5A
is backend-only - see the Stage 5A report). This note is for whoever
builds the Engineering screens next, so they can call the protected
API.

## Authentication

```
POST /api/v1/engineering/login
Content-Type: application/json

{"pin": "...", "engineer_name": "Alfie"}
```

Success (`200`):
```json
{"status": "success", "token": "...", "engineer_name": "Alfie", "expires_at": "2026-09-17T21:00:00+00:00"}
```

- `engineer_name` must be one of: `Alfie`, `Dan`, `Yago`, `Aaron`,
  `Kuri`, `Steve` (exact spelling/capitalisation) - checked server-side
  against `src/main.py`'s `engineers` list, `422` if not recognised.
- `401` - incorrect PIN.
- `429` - too many recent failed attempts from this client (default: 5
  attempts / 15 minute lockout, both configurable via
  `ENGINEERING_LOGIN_MAX_ATTEMPTS` / `ENGINEERING_LOGIN_LOCKOUT_MINUTES`).
- `503` - `ENGINEERING_PIN` is not set on the server.

This is a **separate PIN and a separate session store from
Management** (`src/engineering_auth.py`, not `src/management_auth.py`).
An Engineering token is never valid on any `/api/v1/management/*`
route, and a Management token is never valid on any
`/api/v1/engineering/*` route - both return `401`.

Every other `/api/v1/engineering/*` route requires:
```
Authorization: Bearer <token>
```
Missing or invalid/expired token -> `401`. Tokens expire after 30
minutes by default (`ENGINEERING_SESSION_MINUTES`). Sessions are
in-memory on the API process - they do not survive a server restart.

`POST /api/v1/engineering/logout` (requires a bearer token) revokes it
immediately.

**The authenticated engineer's identity always comes from the session
token, never from a request body field.** None of the request models
below accept an `engineer`/`engineer_name` field - sending one is
simply ignored, since it is never read.

## Fault listing

```
GET /api/v1/engineering/faults
    ?production_line=&machine=&engineer=&fault_status=
```
Requires a bearer token. Returns every fault (`downtime_events` row)
matching the optional filters, each with its `repair_updates` history
nested:

```json
{
  "items": [
    {
      "downtime_event_id": 12,
      "production_run_id": 40,
      "production_line": "Rovema",
      "fault_id": 3,
      "machine": "BV1",
      "reason": "Film Jam",
      "reported_by": "Marina",
      "engineer": "Alfie",
      "production_status": "Ongoing",
      "engineering_status": "Investigating",
      "opened_at": "2026-09-17T14:02:00+00:00",
      "accepted_at": "2026-09-17T14:05:00+00:00",
      "resolved_at": null,
      "duration_minutes": 38.2,
      "duration_is_active": true,
      "repair_updates": [
        {
          "id": 9,
          "engineer": "Alfie",
          "update_type": "Follow Up",
          "repair_classification": "Mechanical",
          "finding": "Film sensor misaligned",
          "action": "Realigned and tested",
          "notes": null,
          "setting_name": null,
          "previous_value": null,
          "new_value": null,
          "reason_for_change": null,
          "affected_products_or_formats": null,
          "engineering_status": "Investigating",
          "created_at": "2026-09-17T14:20:00+00:00"
        }
      ]
    }
  ],
  "total": 1
}
```

`repair_updates[].created_at` is **always a real timestamp, never
`null`** - a live-schema preflight (run ahead of applying migration
`0002`) confirmed `engineering_updates.created_at` already exists in
the production database as `timestamp with time zone, NOT NULL,
DEFAULT now()`. Every row, historical or new, already has one.

`repair_updates[].update_type` is one of the three values already
permitted by the live `chk_engineering_update_type` CHECK constraint:
`Investigation`, `Follow Up`, `Resolution`. This API only ever writes
two of them - `Follow Up` for an interim `/updates` call, `Resolution`
for the final `/close` call - both already accepted by that
constraint, so no schema change was needed for `update_type` at all.

Use `production_status` to split into **Open production faults**
(`"Ongoing"`) vs **Resolved jobs** (`"Resolved"`); use
`engineering_status != "Resolved"` on the open set for **Open
engineering jobs**. Fields deliberately excluded from this response
(present in `downtime_events` but not exposed here): `engineer_called`,
`retrospective` - not part of the approved Engineering workflow.

## Accept / start work

```
POST /api/v1/engineering/faults/{downtime_event_id}/accept
```
No request body - the engineer comes from the session.

- `404` - fault does not exist.
- `409` - fault is already resolved, **or** another engineer already
  holds it (`"...already been accepted by another engineer."`). Both
  cases return the same status code by design - the caller cannot tell
  from the status code alone which happened, only from `detail`.
- `200` - idempotent for the *same* authenticated engineer (repeating
  the call re-confirms the existing assignment without moving
  `accepted_at`).

```json
{"status": "success", "downtime_event_id": 12, "engineer": "Alfie", "engineering_status": "Investigating", "accepted_at": "2026-09-17T14:05:00+00:00"}
```

## Repair updates (interim)

```
POST /api/v1/engineering/faults/{downtime_event_id}/updates
{
  "classification": "Mechanical",
  "finding": "...",
  "action": "...",
  "notes": null
}
```
or, for a Machine Setting change:
```json
{
  "classification": "Machine Setting",
  "finding": "...",
  "action": "...",
  "notes": null,
  "setting_name": "Sealer temperature",
  "previous_value": "185C",
  "new_value": "192C",
  "reason_for_change": "Seal integrity failing at low line speed",
  "affected_products_or_formats": "1kg Pillow Pack - all customers"
}
```

- `classification` must be exactly `"Mechanical"` or `"Machine
  Setting"` - `422` otherwise.
- `finding`, `action` - required, non-blank, trimmed, max 2000
  characters.
- `notes` - optional, trimmed, max 2000 characters.
- Machine Setting fields (`setting_name`, `previous_value`,
  `new_value`, `reason_for_change`, `affected_products_or_formats`) -
  **all required, non-blank** when `classification` is `"Machine
  Setting"`; **all rejected** (must be omitted/blank) when
  `classification` is `"Mechanical"`. `422` on either violation.
- `404` - fault does not exist. `409` - fault already resolved, or not
  accepted by the calling engineer (accept it first).

```json
{"status": "success", "downtime_event_id": 12, "engineering_update_id": 9, "created_at": "2026-09-17T14:20:00+00:00"}
```

## Close fault

```
POST /api/v1/engineering/faults/{downtime_event_id}/close
```
**Same request body shape as `/updates` above** - closing requires the
final repair classification, finding and action (and full Machine
Setting fields if applicable) in the same call that resolves the
fault.

- `404` - fault does not exist.
- `409` - already resolved (by this engineer's own earlier close, or a
  concurrent one that committed first), or not accepted by the calling
  engineer.
- `200` - the final repair-update row and the `Resolved` status change
  commit together, atomically, in one database transaction - see the
  Stage 5A report's "Atomicity and concurrency protections" section
  for exactly how.

```json
{"status": "success", "downtime_event_id": 12, "engineer": "Alfie", "engineering_status": "Resolved", "production_status": "Resolved", "resolved_at": "2026-09-17T15:10:00+00:00"}
```

## CORS / environment

Same two exact origins as the rest of the API (`HMI_ORIGIN`,
`DASHBOARD_ORIGIN`); no change was needed - `POST`/`GET` and
`Authorization` were already allowed by the existing CORS config for
Management.

Required environment variables (names only):
`ENGINEERING_PIN` (required for login to work at all), and optional
overrides `ENGINEERING_SESSION_MINUTES`, `ENGINEERING_LOGIN_MAX_ATTEMPTS`,
`ENGINEERING_LOGIN_LOCKOUT_MINUTES`. See `.env.example`.

## Database migration

`migrations/0002_engineering_workflow.sql` adds the columns this API
needs to `downtime_events` (`accepted_at`) and `engineering_updates`
(`repair_classification`, `setting_name`, `previous_value`,
`new_value`, `reason_for_change`, `affected_products_or_formats`,
`notes`). It has **not** been applied to the live database yet -
review it, then apply it before any of the endpoints above will work
against real data.

**`engineering_updates.created_at` is deliberately NOT part of this
migration.** A read-only Supabase preflight run ahead of applying
`0002` found it already exists in the live schema exactly as needed:
`timestamp with time zone, NOT NULL, DEFAULT now()`. An earlier draft
of `0002` wrongly assumed this column didn't exist yet and proposed
adding it; that assumption was corrected once the live schema was
checked, and the column is now reused exactly as-is - not added,
altered, backfilled or renamed.

**`engineering_updates.update_type` and its CHECK constraint
(`chk_engineering_update_type`) are also deliberately NOT part of this
migration** - the same preflight confirmed the constraint already
permits `Investigation`, `Follow Up` and `Resolution`, which is
everything this API needs.
