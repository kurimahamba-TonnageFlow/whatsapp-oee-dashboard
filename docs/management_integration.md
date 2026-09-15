# Pulse Management — Integration Notes

No Management frontend source exists in this repository (same
situation as the HMI and Dashboard). This note is for whoever builds
the Management pages so they can call the protected API.

## Authentication

```
POST /api/v1/management/login
Content-Type: application/json

{"pin": "...", "manager_name": "Kuri"}
```

Success (`200`):
```json
{"status": "success", "token": "...", "manager_name": "Kuri", "expires_at": "2026-09-15T10:30:00+00:00"}
```

- `401` — incorrect PIN.
- `429` — too many recent failed attempts from this client (default: 5
  attempts / 15 minute lockout, both configurable via
  `MANAGEMENT_LOGIN_MAX_ATTEMPTS` / `MANAGEMENT_LOGIN_LOCKOUT_MINUTES`).
- `503` — `MANAGEMENT_PIN` is not set on the server.

Every other `/api/v1/management/*` route requires:
```
Authorization: Bearer <token>
```
Missing or invalid/expired token → `401`. Tokens expire after 30
minutes by default (`MANAGEMENT_SESSION_MINUTES`). Sessions are
in-memory on the API process - they do not survive a server restart
and are not shared across multiple worker processes if the API is
ever run with more than one.

`POST /api/v1/management/logout` (requires a bearer token) revokes it
immediately.

## Line / machine / button configuration

```
GET    /api/v1/management/lines
POST   /api/v1/management/lines                      {name, display_order?}
PATCH  /api/v1/management/lines/{line_id}             {name?, active?, display_order?}
GET    /api/v1/management/lines/{line_id}/machines
POST   /api/v1/management/lines/{line_id}/machines    {name, display_order?}
PATCH  /api/v1/management/machines/{machine_id}       {name?, active?, display_order?}
GET    /api/v1/management/machines/{machine_id}/buttons
POST   /api/v1/management/machines/{machine_id}/buttons
PATCH  /api/v1/management/buttons/{button_id}
```

Button create body:
```json
{
  "name": "Film Jam",
  "event_type": "unplanned_fault",
  "ownership": "Production",
  "fault_category": null,
  "display_order": 0
}
```
`event_type` is `"planned_downtime"` or `"unplanned_fault"`.
`ownership` is `"Production"` or `"Engineering"`.

Nothing is ever deleted - "removing" a line/machine/button is
`PATCH {"active": false}`. Renames are also `PATCH`. History in
`downtime_events`/`engineering_updates` is untouched by either, since
those reference machines only by the free-text `machine` name they
captured at the time, not a foreign key.

Every create/update writes one row to `management_audit_log`
(`action`, `manager_name`, `record_type`, `record_id`,
`previous_value`, `new_value`, `reason`, `created_at`).

## Active runs + force close

```
GET /api/v1/management/active-runs
```
Returns every currently `Active` run across all three lines (including
any `TEST-` marked ones - Management must be able to see and close
those too), each with an `active_seconds` field.

```
POST /api/v1/management/runs/{run_id}/force-close
{"reason": "Technician left mid-shift", "note": null}
```
`reason` must be one of: `Technician left mid-shift`, `Tablet or
browser closed`, `Run started by mistake`, `Changeover completed`,
`Production stopped`, `Duplicate run`, `Other`. `note` is required
(non-blank) when `reason` is `"Other"`.

- `404` — run does not exist.
- `409` — run is not `Active` (already completed, or another manager
  force-closed it a moment earlier - both look identical to the
  caller, which is the correct behaviour: someone else already
  resolved it).
- `200` — `{"status":"success","run_id","production_line","run_status":"Cancelled","closed_by","reason"}`.

Force-closed runs get `status = 'Cancelled'` (an existing, previously
unused value already permitted by the database's own check
constraint) and `finished_at` set to the close time - never
`'Completed'`, so they stay distinguishable from a normally-finished
run in all dashboard/reporting queries. History is preserved; nothing
is deleted. The line becomes available again immediately (the same
partial unique index that limits a line to one `Active` run also makes
this close atomic and concurrency-safe - a second manager's
force-close attempt on the same run gets `409`, not a silent
double-close).

## Technician performance

```
GET /api/v1/management/technician-performance
    ?period=current_week
    &production_line=&shift=&technician=&product=&customer=
    &date_from=&date_to=
```

`period` is one of `today`, `yesterday`, `current_week`,
`previous_week`, `current_month`, `previous_month`, `current_quarter`,
`previous_quarter`, `current_year`, or omitted/`custom` to use
`date_from`/`date_to` directly. Named periods resolve to whole
calendar-period bounds (e.g. `current_week` = Monday-Sunday of this
week), not "period to date."

Only `Completed` runs are counted (force-closed/`Cancelled` runs are
excluded from performance figures) and `TEST-` marked runs are always
excluded, via the same filter logic the Dashboard API already uses.

Response:
```json
{
  "period": "current_week",
  "date_from": "2026-09-08",
  "date_to": "2026-09-14",
  "minimum_sample_size": 3,
  "ranked": [ { "line_technician": "Ben", "completed_runs": 5, "target_achievement_percent": 96.0, "label": "On target", "lines": ["Rovema"], "run_ids": [6,7,8,9,10] } ],
  "insufficient_data": [ { "line_technician": "NewTechnician", "completed_runs": 1, "label": "Insufficient data" } ]
}
```

- Ranked **by `target_achievement_percent`** (actual ÷ expected for
  that technician's own runs), never raw pallet/tonne totals.
- Technicians with fewer than `minimum_sample_size` (default 3,
  `MANAGEMENT_MIN_SAMPLE_RUNS`) Completed runs in range appear only in
  `insufficient_data`, always labelled `"Insufficient data"`.
- `target_achievement_percent` and `data_completion_rate_percent` are
  `null` (never `0`) when there's no expected-output data to divide
  by - missing data is never presented as zero performance.
- `data_completion_rate_percent` = percentage of the technician's
  Completed runs with at least one `hourly_updates` row - a coarse,
  honestly-labelled proxy for "did they submit updates," not a claim
  of precise data quality.
- Labels are `"On target"` (≥95%), `"At risk"` (80-95%), `"Needs
  review"` (<80%), or `"Insufficient data"` - never a raw score
  presented as a verdict.
- To drill into the runs behind a result, use the **existing**
  Dashboard endpoint: `GET /api/v1/dashboard/runs?technician=<name>`
  (already supports this filter - no separate drill-down endpoint was
  built here).

## Public HMI configuration (no auth)

```
GET /api/v1/hmi/config
```
Returns only active lines → active machines → active buttons - never
Management data (audit log, sessions, disabled rows) or credentials.
The operator HMI should poll this so a newly added button appears
after a refresh without republishing the HMI. See
`docs/hmi_integration.md` for the response shape.

## CORS / environment

Same two exact origins as the rest of the API (`HMI_ORIGIN`,
`DASHBOARD_ORIGIN` - a Management UI hosted at either origin works
today; if it ends up on a third origin, add it the same way). CORS now
also allows the `PATCH` method and `Authorization` header, both
required by Management and not previously enabled.

Required environment variables (names only):
`MANAGEMENT_PIN` (required for login to work at all), and optional
overrides `MANAGEMENT_SESSION_MINUTES`, `MANAGEMENT_LOGIN_MAX_ATTEMPTS`,
`MANAGEMENT_LOGIN_LOCKOUT_MINUTES`, `MANAGEMENT_MIN_SAMPLE_RUNS`.

## Database migration

`migrations/0001_management_area.sql` adds four new tables
(`production_lines`, `machines`, `buttons`, `management_audit_log`).
It has **not** been applied to the live database yet - review it, then
apply it (e.g. via Supabase's migration tooling) before any of the
config endpoints above will work against real data.
