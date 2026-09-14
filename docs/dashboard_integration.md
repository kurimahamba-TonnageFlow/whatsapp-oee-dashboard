# Pulse Dashboard — Read API Integration

No dashboard frontend source exists in this repository (confirmed by
scanning the tree during the earlier diagnostic). This note is for
whoever maintains the dashboard at
https://tonnage-flow-pulse-dashboard.kurirai-mahamba.chatgpt.site.

Base path: `/api/v1/dashboard`. All endpoints are `GET`, read-only.

## Endpoint list

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/dashboard/filter-options` | Values to populate every filter dropdown |
| GET | `/api/v1/dashboard/runs` | Paginated list of Production Runs |
| GET | `/api/v1/dashboard/runs/{run_id}` | Single Production Run detail |
| GET | `/api/v1/dashboard/summary` | Aggregate KPIs across matching runs |
| GET | `/api/v1/dashboard/output-timeline` | Per-hour expected/actual output |
| GET | `/api/v1/dashboard/planned-downtime` | Planned downtime minutes by category |
| GET | `/api/v1/dashboard/engineering-downtime` | Engineering response / unplanned downtime metrics |
| GET | `/api/v1/dashboard/faults` | Downtime event (fault) list with computed duration |
| GET | `/api/v1/dashboard/quality-events` | Always reports data unavailable (see below) |
| GET | `/api/v1/dashboard/export` | CSV export of the Runs dataset |

## Query parameters

All list/aggregate endpoints (everything except `/runs/{run_id}` and
`/quality-events`) accept these optional filters:

| Parameter | Applies to | Column | Match |
| --- | --- | --- | --- |
| `date_from`, `date_to` | all | `production_runs.started_at::date` (runs/hourly-based endpoints) or `downtime_events.opened_at::date` (fault/engineering endpoints) | inclusive day range |
| `production_line` | all | `production_runs.production_line` | exact |
| `shift` | all | `production_runs.shift` | exact |
| `product` | all | `production_runs.product` | exact |
| `customer` | all | `production_runs.customer` | exact |
| `technician` | all | `production_runs.line_technician` | exact |
| `run_status` | all | `production_runs.status` (`Active`/`Completed`) | exact |
| `machine` | faults, engineering-downtime | `downtime_events.machine` | partial (`ILIKE %value%`) - it's free text |
| `engineer` | faults, engineering-downtime | `downtime_events.engineer` / `engineering_updates.engineer` | exact |
| `fault_status` | faults, engineering-downtime | `downtime_events.production_status` (`Ongoing`/`Resolved`) | exact |
| `downtime_type` | planned-downtime, output-timeline, summary | `hourly_updates.planned_downtime` | exact |
| `engineering_class` | engineering-downtime | `engineering_updates.update_type` (`Investigation`/`Follow Up`/`Resolution`) | exact |
| `format` | **none - unsupported** | no reliable column exists | accepted, always ignored |

`/runs` additionally accepts `page` (default 1) and `page_size`
(default 25, max 100).

**Unsupported filter**: `format` has no reliable column mapping
anywhere in the current schema (`pack_type` is the closest concept but
is not the same thing, and guessing the mapping was explicitly avoided
per instruction). It is accepted on every endpoint so callers never get
a 422 for sending it, but it is never applied. `filter-options`'
`unsupported_filters` field lists it explicitly.

## Response examples

`GET /api/v1/dashboard/summary`
```json
{
  "total_runs": 3,
  "expected_pallets": 100.0,
  "actual_pallets": 80.0,
  "expected_tonnes": 40.0,
  "actual_tonnes": 32.0,
  "output_gap_pallets": 20.0,
  "output_gap_tonnes": 8.0,
  "target_achievement_percent": 80.0,
  "planned_downtime_minutes": 45.0,
  "unplanned_downtime_minutes": 30.0,
  "unplanned_downtime_includes_active_faults": true,
  "estimated_lost_packs": 500.0,
  "estimated_lost_minutes": 25.0,
  "estimated_lost_pallets": 2.5,
  "estimated_lost_tonnes": 1.25,
  "open_faults": 1,
  "resolved_faults": 4,
  "machine_setup_minutes": null,
  "machine_repair_minutes": null,
  "machine_classification_status": "not_captured"
}
```

`GET /api/v1/dashboard/runs`
```json
{
  "items": [
    {
      "run_id": 1,
      "production_line": "Rovema",
      "line_technician": "Marina",
      "shift": "Night",
      "customer": "Asda",
      "product": "Basmati",
      "pack_type": "Pillow",
      "status": "Active",
      "started_at": "2026-01-01T08:00:00+00:00",
      "finished_at": null,
      "pallets_remaining": 10,
      "total_pallets_completed": 5,
      "changeover_type": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25
}
```

`GET /api/v1/dashboard/quality-events`
```json
{
  "items": [],
  "total": 0,
  "data_status": "not_available",
  "message": "Quality events are not captured by the current Pulse data model."
}
```

`GET /api/v1/dashboard/runs/{run_id}` on an unknown/excluded id → `404`
```json
{ "detail": "Production Run not found." }
```

A database-read failure on any endpoint → `503`
```json
{ "detail": "Dashboard data is temporarily unavailable. Please try again." }
```
No response body, and nothing printed to logs, ever includes the
underlying exception text, connection strings, or credentials.

## Calculation definitions

- **Expected/Actual pallets**: `SUM(hourly_updates.expected_pallets)` /
  `SUM(hourly_updates.actual_pallets)`. Deliberately **not**
  `production_runs.total_pallets_completed`, whose overrun handling
  differs once a run exceeds its planned quantity.
- **Tonnes**: `pallets × cases_per_pallet × packs_per_case ×
  pack_weight_kg ÷ 1000`, using each run's own packing configuration.
- **Output gap**: `MAX(expected − actual, 0)`.
- **Target achievement %**: `actual ÷ expected × 100`, or `null`
  (never `0`) when expected is `0`. Never sourced from
  `hourly_updates.oee`, which is a separately, manually reported figure
  (Pulse's README explicitly states Reported OEE ≠ Calculated
  Production Performance).
- **Planned downtime**: `SUM(hourly_updates.planned_downtime_minutes)`,
  grouped by `hourly_updates.planned_downtime`.
- **Unplanned downtime**: for each fault, `resolved_at − opened_at` if
  resolved, else `NOW() − opened_at` (server UTC time) if still open.
  Open-fault durations are marked `duration_is_active: true` /
  `unplanned_downtime_includes_active_faults: true` so the dashboard can
  visually distinguish a still-growing duration from a final one. This
  is **not** the same number as `hourly_updates.estimated_lost_minutes`
  (see below) and the two must never be substituted for each other.
- **Estimated output lost**: the stored `hourly_updates
  .estimated_lost_packs` / `.estimated_lost_minutes`, plus pallets/
  tonnes derived from them using each run's own packing configuration
  (`estimated_lost_packs ÷ packs_per_case ÷ cases_per_pallet` for
  pallets; `estimated_lost_packs × pack_weight_kg ÷ 1000` for tonnes).
  These are estimates of production-time-equivalent shortfall, labeled
  as such - not a direct downtime duration.

## Unsupported MVP data

- **Machine Setup vs Machine Repair downtime**: the schema has no
  reliable classification for this (no such category exists in
  `hourly_updates.planned_downtime`, and `downtime_events.machine`/
  `.reason` are unconstrained free text). Every response that would
  carry this breakdown (`/summary`, `/engineering-downtime`) instead
  returns:
  ```json
  { "machine_setup_minutes": null, "machine_repair_minutes": null, "machine_classification_status": "not_captured" }
  ```
- **Quality events**: no `quality_events` table or any quality/defect
  column exists anywhere in the schema. `/quality-events` always
  returns the fixed "not available" shape documented above rather than
  inventing zero-value KPIs.
- **Repeat faults**: intentionally not implemented in this pass -
  `downtime_events.machine`/`.reason` are free text with no fault
  taxonomy, so grouping would be unreliable pattern-matching rather
  than a real calculation. Flagged in the original diagnostic; no
  endpoint here claims to detect this.
- **Per-hour timestamps**: `hourly_updates` has no timestamp column at
  all. `/output-timeline` orders by submission sequence
  (`sequence_in_run`, derived from row `id`), not wall-clock time - this
  is stated explicitly in that endpoint's `note` field.
- **Engineering-update timestamps**: `engineering_updates` also has no
  timestamp column; its date filtering is approximated via its parent
  `downtime_events.opened_at`.

## Test-data exclusion rule

Every dashboard query excludes rows where any of these hold (applied
via `_TEST_DATA_EXCLUSION_SQL`, centralised in `src/database.py` and
used by every query condition-builder - `_run_conditions`,
`_fault_conditions`, `_engineering_conditions`):

```sql
production_line NOT ILIKE 'TEST-%'
AND customer NOT ILIKE '%TEST-%'
AND product NOT ILIKE '%TEST-%'
AND shift NOT ILIKE '%TEST-%'
```

This is a naming **convention** inferred from this project's own
test/verification scripts, not a database flag - no rows are deleted,
and a real technician typing "TEST" into a free-text field would
(rarely) be excluded too. `GET /api/v1/dashboard/runs/{run_id}` applies
the same rule, so a test run's id returns `404` from the dashboard even
though the row still exists in Supabase.

## CORS configuration

`src/api.py` sets a fixed, two-item allow-list - never a wildcard:

```python
allow_origins=[HMI_ORIGIN, DASHBOARD_ORIGIN]
```

Both are read from the environment with the current production URLs as
defaults:
- `HMI_ORIGIN` → `https://tonnage-flow-pulse-hmi.kurirai-mahamba.chatgpt.site`
- `DASHBOARD_ORIGIN` → `https://tonnage-flow-pulse-dashboard.kurirai-mahamba.chatgpt.site`

## Local startup command

```
uvicorn src.api:app --reload
```
Run from the repository root (the parent of `src/`), not from inside
`src/`. Local Swagger UI: `http://127.0.0.1:8000/docs`.

## Required environment-variable names

`DATABASE_URL`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ALLOWED_GROUP`,
`HMI_ORIGIN`, `DASHBOARD_ORIGIN`. See `.env.example` for the template
(values are never committed).
