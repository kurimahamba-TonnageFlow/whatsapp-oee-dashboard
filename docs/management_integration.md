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
minutes by default (`MANAGEMENT_SESSION_MINUTES`); nothing extends
them.

`POST /api/v1/management/logout` (requires a bearer token) revokes it
immediately.

`GET /api/v1/management/session` (requires a bearer token) confirms a
token is still live: `200 {"status", "manager_name", "expires_at"}`
with the expiry set at login, or `401`. It never extends the session.

### Sessions, refresh and restarts

- **Browser refresh keeps the manager signed in.** The React app keeps
  `{token, managerName, expiresAt}` in the tab's `sessionStorage`
  (`pulse.management.session.v1`) - never the PIN, never
  `localStorage`, `IndexedDB` or a cookie. On a refresh the page shows
  "Checking your Management session…" and calls
  `GET /api/v1/management/session`; only a `200` restores the session.
  A `401` (expired, revoked or unknown token) returns to sign-in with
  "Your Management session has expired"; any other failure returns to
  sign-in without trusting the stored token. Closing the tab forgets
  the token; Log Out, a `401` from any call, or leaving the Management
  area clears it and revokes it server-side.
- **Sessions and PIN lockouts live in the API process's memory.** An
  API restart or redeploy signs every manager (and engineer) out; their
  next request or refresh returns them to sign-in. Lockout counters
  also reset on restart.
- **The API must run as exactly one worker process.** With more than
  one worker (`uvicorn --workers N`, gunicorn with several workers, or
  several containers behind a load balancer) a token issued by one
  worker is unknown to the others, so managers are signed out at
  random and lockouts can be bypassed by landing on another worker.
  Moving sessions to the database would be needed before scaling out.
- **Lockout is keyed by the client address the API sees.** Behind a
  reverse proxy that is the proxy's address unless uvicorn is started
  with `--proxy-headers --forwarded-allow-ips=<proxy address>`; without
  that, one person's wrong PINs lock every manager out for 15 minutes.

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
those too), each with `active_seconds`, `last_hourly_update_at`,
`hourly_update_count`, `open_planned_stop_reason` /
`open_planned_stop_started_at`, `open_changeover_id` and
`open_line_fault_count` (faults open on the line from any run).

The Management **Active runs** page (`/management/active-runs`) lists
these and force-closes a run only after a reason (and a note for
Other) and a confirmation step that states the consequences below.

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
- `409` — a changeover is open on the run. It must be completed on the
  line tablet (Changeover Complete) first; a changeover has no
  truthful "abandoned" state.
- `200` — `{"status":"success","run_id","production_line","run_status":"Cancelled","finished_at","closed_by","reason","ended_planned_stop"}`.

Force-closed runs get `status = 'Cancelled'` (an existing, previously
unused value already permitted by the database's own check
constraint) and `finished_at` set to the close time - never
`'Completed'`, so they stay distinguishable from a normally-finished
run in all dashboard/reporting queries. History is preserved; nothing
is deleted. The close is one transaction with the run row locked, so a
second manager's force-close attempt on the same run gets `409`, not a
silent double-close.

What a force-close does and does not do:

- **No output is invented.** No hourly rows are written; hours nobody
  reported stay "no reading" in the hourly report.
- **An open planned stop is ended at the close time** (`ended_by` =
  "<manager> (manager force-close)"), as End Run would require - left
  open it would keep counting with no run behind it.
- **Open faults are untouched.** They belong to the line, stay open for
  Engineering, and the next technician must acknowledge them before
  starting a run.
- **The line then needs its next step** (End Shift, Changeover, Other or
  Not scheduled), recorded by the next technician on the tablet or by a
  manager on the Production dashboard ("Run ended — next step not
  chosen"). It starts at the force-close time. Start Run is refused
  until then.
- **Audit:** one `management_audit_log` row (`force_close_run`) with the
  manager, reason, the run before, and the run after including any
  planned stop it ended. The audit write happens after the close
  commits and a failure there is logged, not raised - the run is
  still closed.

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


### Management production standards (local change)

Management owns versioned production speed standards. Changes apply only to new runs from their effective time. Start Run no longer accepts a technician-defined baseline: any legacy speed field is ignored, and the database selects the applicable configuration version. A missing management standard prevents starting a new run. Existing run snapshots and operating-speed reports are unchanged. See `production_standard_reconciliation.md` for configuration matching, API contracts and the required local migration.


## Management snag corrections ? 2026-10-05 (local)

This section supersedes the earlier technician-performance calculation and force-close audit descriptions. Performance selects complete runs by their London start date and includes each selected run in full. `technician_reports.build_technician_performance` uses the shared fixed-standard reconciliation. Achievement uses comparable nominal tonnes, not a sum of unlike pallet formats. Gaps sum positive period shortfalls. `reported_tonnes` retains known actual output even where a historical standard or reading interval is unknown. `coverage_complete` and `limitations` describe comparability; incomplete evidence is unranked. `data_completion_rate_percent` measures timed comparable reading coverage of run duration, not simply the percentage of runs containing any reading.

Planned and line-wide unplanned stop intervals are clipped and unioned per run, with planned precedence. Faults carried from earlier runs are included; production restart ends downtime regardless of Engineering closure. Between-run stops are not assigned to a run technician. This is production evidence, not competence or individual responsibility.

Force-close now inserts the manager, reason and locked before/after snapshot in the closure transaction. Audit failure rolls back the entire action. Factory setup and weekly-target configuration API audits also commit in the same transaction. Update snapshots are read under a row lock; weekly-target batches hold a transaction-scoped advisory lock by week, including first creation. Audit failure rolls back the change. No schema migration is required for this correction.


## Rovema task-performance evidence (2026-10-06)

Performance now includes a management-session-protected, read-only matrix at GET /api/v1/management/task-performance. It covers the seven agreed tasks and the full Rovema roster. Scope is a separate rolling 90-day task-start window, not the production-run filters. Existing timestamped planned stops are reused; exact task labels and CCP Check are recognised. Unknown reasons are disclosed as excluded. Cancelled and configured test runs are excluded.

All cells remain grey until reference times, minimum samples and colour thresholds are agreed. No worker competence, fault responsibility or automatic speed ranking is inferred. The timer initiator is the reporting identity, not a verified performer. Details preserve start/end actors and times, including unfinished records, and median completed elapsed times grouped by product and pack configuration. Waiting and shared work are not separated in existing evidence. Casepacker requests, breakdowns and between-run changeovers are not reassigned as technician task durations.

This is the agreed evidence-gathering first stage. Dedicated task/performer/delay capture, approved comparison rules, trend evaluation and automatic colours remain future work. No migration or manual rating editor is introduced.

User confirmed evidence collection first: a separate benchmarking tracker displays fastest, median and slowest completed timer observations and sample counts per reporter/task/product/pack configuration. These observations do not set targets or colours. Benchmark definitions will be reviewed later.
