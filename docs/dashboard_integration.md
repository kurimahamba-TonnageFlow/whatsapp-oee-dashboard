# Pulse Dashboard — Read API Integration

Base path: `/api/v1/dashboard`. All endpoints are `GET`, read-only, and
(since Stage 6B1) **require a Management session**. The permanent
management dashboard is being built inside this repository's React app
at `/dashboard` (Stage 6C onward).

## Status (Stage 6B1)

- **Backend contracts: implemented and offline-tested.**
- **Migration `migrations/0003_pulse_phase1_foundation.sql`: applied
  successfully during Stage 6B4.** Every Stage 6B1 endpoint below (and
  the new HMI capture endpoints in `docs/hmi_integration.md`) needs it.
  It was applied once with psql after a verified backup, and is not
  recorded in `supabase_migrations.schema_migrations`.
- **React HMI integration: pending (Stage 6B2).** Until the HMI sends
  hourly updates, planned downtime, fault reports and X-ray counts to
  the capture endpoints, the window-based reports only contain data
  captured some other way.
- **React dashboard pages: not built yet** (Stage 6C/6D).

## Authentication (Stage 6B1)

Every `/api/v1/dashboard/*` route requires
`Authorization: Bearer <token>`, where the token comes from the existing
`POST /api/v1/management/login` (server-checked Management PIN - see
`docs/management_integration.md`). There is no second auth system and
no dashboard-specific PIN.

| Situation | Response |
| --- | --- |
| No / malformed `Authorization` header | `401 {"detail": "Management session required."}` |
| Unknown, expired or Engineering token | `401 {"detail": "Management session is invalid or has expired."}` |
| Invalid query (unknown window, unknown line, non-Monday week, bad filter) | `422` |
| Database read failure | `503 {"detail": "Dashboard data is temporarily unavailable. Please try again."}` |

No role model exists yet, so `403` is not used: any valid Management
session may read all dashboard data. Error bodies and logs never contain
exception text, connection strings or credentials.

**Compatibility impact:** the external dashboard at
`https://tonnage-flow-pulse-dashboard.kurirai-mahamba.chatgpt.site`
previously read these routes with no credentials. It now gets `401` for
every route. `DASHBOARD_ORIGIN` stays in the CORS allow-list (and
`Authorization` is an allowed header), so that origin can still work if
it logs in via the Management API; otherwise it should be retired in
favour of the React `/dashboard`.

## Factory time (Europe/London)

All window boundaries are Europe/London wall-clock time, converted to
UTC through the tz database (`src/factory_time.py`), so GMT and BST are
both correct and no fixed offset is ever used.

| Window (`?window=`) | Definition | Default for |
| --- | --- | --- |
| `current_shift` | Day 06:00-14:00, Afternoon 14:00-22:00, Night 22:00-06:00 | `/overview`, `/lines` |
| `factory_day` | 06:00 to 06:00 the next day | - |
| `production_week` | Monday 06:00 to the following Monday 06:00 | - |
| `rolling_24h` | exactly 24 hours ending now | `/gap-attribution`, `/machines`, `/engineering-classification`, `/xray-waste` |

A Night shift or week that spans a clock change is genuinely 7/9 hours
(or 167/169 hours) long and is reported as such. Every window-based
response includes `window` (`kind`, `label`, `start`, `end` in UTC and
in London local time) and `generated_at`.

## Endpoint list

| Path | Purpose | Since |
| --- | --- | --- |
| `/overview` | Site output, gap attribution, estimated OEE, freshness and one summary per line | 6B1 |
| `/lines` | Per-line summaries only | 6B1 |
| `/gap-attribution` | Estimated planned / unplanned / other / unexplained split of the output gap, per site and line, ranked by tonnes | 6B1 |
| `/machines` | Per-machine fault counts, downtime and estimated tonnes lost (no machine OEE - see below) | 6B1 |
| `/engineering-classification` | Faults by repair classification, maintenance preventability and open/closed | 6B1 |
| `/xray-waste` | End-of-shift / run X-ray captures and combined estimated waste | 6B1 |
| `/weekly-targets` | Site and per-line weekly tonnage progress (`?week_start=` a Monday) | 6B1 |
| `/changeovers` | QC changeover list with filters and grouping | 6B1 |
| `/filter-options`, `/runs`, `/runs/{run_id}`, `/summary`, `/output-timeline`, `/planned-downtime`, `/engineering-downtime`, `/faults`, `/quality-events`, `/export` | Original (pre-6B1) read API - unchanged apart from now requiring authentication | 5 |

Weekly targets are **set** through
`GET/POST /api/v1/management/weekly-targets` (Management session,
audit-logged): body
`{"week_start": "2026-09-21", "targets": [{"scope": "site", "target_tonnes": 400}, {"scope": "line", "production_line": "Rovema", "target_tonnes": 150}]}`.
`week_start` defaults to the current production week and must be a
Monday. A target applies only to its own week - nothing is carried
forward automatically.

## Authoritative calculations

All manufacturing figures are calculated in `src/pulse_calculations.py`
with `decimal.Decimal` end to end. The frontend formats and displays
them; it must not recalculate them.

**Rounding:** only when a value leaves the backend, `ROUND_HALF_UP`, to
packs 2 dp, pallets 4 dp, tonnes 3 dp, minutes 1 dp, percentages 1 dp.
Stored pallet/pack values use `numeric(14,4)`. Decimal pallets such as
`3.75` are exact and carry through any number of hourly updates without
drift.

### Output (measured)

- Packs per pallet = `packs_per_case x cases_per_pallet`.
- Expected packs (per hourly update) = `target_speed_ppm x reported period minutes`
  (the actual elapsed period, not a fixed 60 minutes).
- Actual packs = `pallets_produced x packs per pallet` (confirmed palletised output).
- Pallets = packs / packs per pallet; tonnes = `packs x pack_weight_kg / 1000`,
  each using that run's own configuration.
- Output gap = `max(expected - actual, 0)` in packs, pallets and tonnes.
- **Production achievement %** = `actual tonnes / expected tonnes x 100`
  (tonnes-weighted so different pack sizes combine; identical to the
  packs ratio for a single run), or `null` when nothing was expected.
  **It is not OEE** and is never labelled as OEE.

An hourly update belongs to a window by the **end** of its reported
period; its whole period's output is counted.

Legacy hourly updates have a submission timestamp, but they do not have
a captured period start and period end. They remain excluded from
reporting that requires a reliable production period. (`created_at` has
always existed and is `NOT NULL` on every historical row; migration 0003
leaves it untouched.) They are counted in
`legacy_hourly_updates_without_timestamp`, never guessed -
`period_started_at` and `period_ended_at` are never derived from
`created_at`, because a submission time is not a period boundary.

### Excluded legacy records (`data_quality`)

Those rows are left exactly as they are: nothing is backfilled and no
period time is invented. The consequence is that a window covering that
period reports a total **lower** than the factory actually produced, so
every report carrying a total also carries a `data_quality` block that
says so plainly:

```json
{
  "data_quality": {
    "legacy_records_excluded": true,
    "legacy_record_count": 37,
    "message": "37 older hourly updates could not be included. They have a submission timestamp, but they do not have a captured period start and period end, so they cannot be placed in a shift, day or week. They remain excluded from reporting that requires a reliable production period. Totals for any window covering that time are lower than what was actually produced. The original records are unchanged and no period times have been estimated."
  }
}
```

When nothing is excluded the block is still present, with
`legacy_records_excluded: false`, `legacy_record_count: 0` and
`message: null` - so a consumer never has to infer the difference
between "complete" and "not checked".

The block appears on the overview, gap-attribution, machine-summary,
engineering-classification, X-ray-waste and weekly-target reports. A
dashboard must show the message wherever it shows one of those totals; a
low figure must never be presented as though it were complete.

### Gap attribution (estimated)

`calculation_status: "estimated"` plus a `method` string on every
response.

1. Downtime intervals are clipped to the run, to the selected window
   and to the run's reported hourly periods - downtime outside any of
   those is never counted.
2. Overlapping events are merged; time covered by planned downtime is
   never counted again as unplanned.
3. Minutes are converted to lost packs at the run's own target rate
   (`target_speed_ppm x minutes`), then to pallets and tonnes.
4. Planned downtime is attributed first, then unplanned, **capped** so
   the total can never exceed the measured output gap. The uncapped
   potential is also returned (`uncapped_downtime_potential`).
5. The remainder stays visible, split into `other_or_speed_loss`
   (shortfall in hourly periods where the technician recorded a loss
   reason) and `unexplained_gap`.
6. `by_machine` / `by_planned_reason` share the capped totals by each
   one's own minutes, so they always sum to the capped total. Rankings
   are by estimated tonnes lost.

Minutes are always returned alongside estimated packs/pallets/tonnes.

### Estimated OEE

Returned per line and site as `availability_percent`,
`performance_percent`, `estimated_quality_percent`,
`estimated_oee_percent`, `calculation_status`
(`estimated` / `partial` / `unavailable`), `calculation_method` and
`unavailable_reason`.

- Availability = run time / planned production time, where planned
  production time = reported period minutes - planned downtime, and run
  time = planned production time - unplanned downtime.
- Performance = (actual packs / target packs per minute) / run time.
- Estimated Quality = palletised packs / X-ray pack count, from X-ray
  captures recorded in the window. It covers only post-X-ray losses.
- If any factor lacks captured inputs, it and Estimated OEE are `null`
  with a reason. **Quality is never assumed to be 100%.**

### End-of-shift / run X-ray waste (estimated)

- Palletised packs = pallets in the hourly updates the capture covers
  (everything since the run's previous capture) x packs per pallet.
- Post-X-ray pack difference = X-ray pack count - palletised packs.
- Estimated post-X-ray waste % = difference / X-ray count x 100.
- A Phase 1 ballpark: it does not include rejects before the X-ray.
- Count unavailable: a reason is stored and no waste is calculated
  (`waste_status: "unavailable"`).
- Palletised > X-ray count: saved with
  `waste_status: "data_quality_warning"`, the negative difference and a
  warning - never forced to zero.

### Weekly tonnage target status

- `expected_tonnes_by_now` = target x fraction of the Monday 06:00 -
  Monday 06:00 week elapsed (linear across the whole week).
- `green` when actual tonnes >= expected tonnes by now; `red` when
  behind; `grey` when no target is set or no timestamped production
  data exists yet that week. The final percentage alone never decides
  the colour.
- Also returned: `target_tonnes`, `actual_tonnes`, `tonnes_remaining`,
  `percent_complete`, `week_elapsed_percent`, week start/end,
  `generated_at`, `latest_activity_at`.

### Line attention status

| Status | Rule |
| --- | --- |
| `red` | any open fault on the line, or production achievement below 85% |
| `amber` | achievement 85% to below 95% |
| `green` | achievement 95% or above |
| `grey` | no production data in the window (and no open fault) |

Always returned with `attention_explanation`.

### Data freshness

- `generated_at` - when the response was built.
- `latest_activity_at` - latest real recorded timestamp for the line
  (run start/finish, hourly update, fault open/accept/resolve,
  engineering update, planned stop, X-ray capture). Never fabricated.
- `last_hourly_update_at` - latest `hourly_updates.created_at`.
- `stale_status` - `current`, `stale` (an active run with no hourly
  update for more than 75 minutes, measured from the last update or the
  run start), `no_active_run` or `unknown`. The site is `stale` if any
  line is.

### Machine-level honesty

Faults and downtime keep their machine (free-text `machine`, plus
`machine_id`/`button_id` for React HMI reports), so `/machines` shows
per-machine fault counts, downtime minutes and capped estimated tonnes
lost. **Production achievement and Estimated OEE stay line-level**:
true machine-level OEE would need per-machine output counts (packs
passing each machine) and per-machine ideal rates, which Pulse does not
capture. Every machine row returns `machine_oee: null` with that reason.

### Engineering classification

From each fault's latest classified repair update and its closure
answer: `machine_setup_or_setting` (Machine Setting),
`physical_component_failure` (Mechanical), `not_classified`;
maintenance preventability `yes` / `no` / `unsure` / `not_recorded`;
`open` / `closed`. Preventability is never inferred from free text.

### Changeovers (QC)

A changeover starts at Start Changeover and ends when the first
acceptable packs of the new run are produced. Filters: `date_from` /
`date_to` (factory days, 06:00 London), `production_line`,
`technician`, `shift`, `customer`, `product`, `format`,
`pack_weight_kg` (these four match the previous or the new value),
`status`, `min_duration_minutes`, `max_duration_minutes`. `group_by`:
`line`, `technician`, `shift`, `customer`, `product`, `pack_weight`,
`format`, `day` (factory day), `week` (production week), `month`, or
`duration` (bands under 15 / 15-30 / 30-60 / 60+ minutes, plus `open`).

## Original (pre-6B1) endpoints

Unchanged except for authentication. They aggregate all runs
(optionally filtered by `date_from`/`date_to` on `started_at::date` and
the other filters below), not London windows, and use SQL-side sums.

| Parameter | Applies to | Column | Match |
| --- | --- | --- | --- |
| `date_from`, `date_to` | all | `production_runs.started_at::date` or `downtime_events.opened_at::date` | inclusive day range |
| `production_line`, `shift`, `product`, `customer`, `technician`, `run_status` | all | `production_runs.*` | exact |
| `machine` | faults, engineering-downtime | `downtime_events.machine` | partial (`ILIKE`) |
| `engineer`, `fault_status` | faults, engineering-downtime | `downtime_events.*` | exact |
| `downtime_type` | planned-downtime, output-timeline, summary | `hourly_updates.planned_downtime` | exact |
| `engineering_class` | engineering-downtime | `engineering_updates.update_type` | exact |
| `format` | none | accepted, ignored on these legacy routes | - |

`/runs` also takes `page` (default 1) and `page_size` (default 25, max
100). `/quality-events` always reports `data_status: "not_available"`.
`/summary`'s `machine_setup_minutes` / `machine_repair_minutes` remain
`null` with `machine_classification_status: "not_captured"`; use
`/engineering-classification` instead. Hourly updates written through
the Stage 6B1 capture endpoint also store their overlapping planned
downtime minutes, so `/summary`'s planned-downtime total stays
coherent.

## Test-data exclusion rule

Every dashboard query excludes rows where any of these hold (the
centralised `_TEST_DATA_EXCLUSION_SQL` in `src/database.py`):

```sql
pr.production_line NOT ILIKE 'TEST-%%'
AND pr.customer NOT ILIKE '%%TEST-%%'
AND pr.product NOT ILIKE '%%TEST-%%'
AND pr.shift NOT ILIKE '%%TEST-%%'
```

`%%` is deliberate: this fixed fragment is spliced into queries that are
executed with bound parameters, and psycopg treats a single `%` as the
start of a placeholder. `%%` is psycopg's escaped literal `%`, so the
database receives `'TEST-%'`. Changeovers apply the same convention to
their line, customer and product columns. It is a naming convention, not
a database flag - no rows are deleted.

## CORS

`src/api.py` allows exactly `HMI_ORIGIN` and `DASHBOARD_ORIGIN` (never a
wildcard), methods `GET`, `POST`, `PATCH`, `OPTIONS`, headers
`Content-Type` and `Authorization`. Unchanged in Stage 6B1.

## Local startup

```
uvicorn src.api:app --reload
```

Run from the repository root. Required environment variables:
`DATABASE_URL`, `MANAGEMENT_PIN`, `ENGINEERING_PIN`,
`WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ALLOWED_GROUP`, `HMI_ORIGIN`,
`DASHBOARD_ORIGIN` (see `.env.example`; values are never committed).
