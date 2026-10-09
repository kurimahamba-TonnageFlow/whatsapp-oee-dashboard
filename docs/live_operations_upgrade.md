# Live Operations Dashboard - review delivery

Status: implemented in `feature/linetech-preview`, local preview only. No commit, push, merge, deployment or live migration was performed for this dashboard task. Existing uncommitted LineTech setup work remains separate in the same checkout.

## What changed

`/dashboard` now presents the live recorded factory view: weekly production progress, five summary cards, configured production-line cards, achievement donuts, eight completed-hour trends, ongoing issues, seven-day breakdowns and changeover readiness. The original detailed production dashboard remains available at `/dashboard?view=reports`.

The existing dark dashboard shell, navigation, session handling and design tokens are retained. Charts use SVG/CSS; no chart package, production dependency or service was introduced. HMI recording, WhatsApp cards/delivery, production standards and Engineering workflows were not changed by this dashboard task.

Management has a working Weekly targets page. It records the factory target, effective week, selected start weekday and notes, with the existing manager identity and audit log. Previous weeks remain available. A target is not automatically copied into another week.

The supplied request did not include a dashboard mock-up. This preview follows its written layout and the existing Pulse theme. Visual matching to an approved mock-up remains unverified and needs your review.

## Metric sources and rules

| Display | Existing source and calculation |
| --- | --- |
| Configured lines | Active `production_lines`, ordered by configured display order. No hardcoded customer or product in production code. |
| Current shift | Shared Europe/London factory-time boundaries: 06:00, 14:00, 22:00. The existing Day shift is displayed as Morning. Midnight and daylight-saving handling remain shared. |
| Weekly produced tonnes | Confirmed `hourly_updates.pallets_completed` multiplied by each run's historical cases per pallet, packs per case and pack weight, divided by 1,000. Latest version per run/hour wins. Partial pallets retain precision. These are produced tonnes, not dispatched tonnes. |
| Week membership | Existing recorded operational-shift membership. Whole hourly readings stay with their recorded shift; crossing readings are disclosed. The effective reporting weekday follows the latest applicable site target; before any target, Monday is the default. |
| Weekly target | Existing `weekly_tonnage_targets`, `scope=site`. No target is fabricated. Above-target percentage is retained; only the bar fill is capped. |
| Last-hour OEE | Existing `hourly_reports.build_hourly_report` and `pulse_calculations`. Actual packs / expected packs x 100. This is the agreed output-achievement metric, explicitly distinguished from classical Availability x Performance x Quality. Fixed approved run standards and existing line-stop target rules are preserved. Planned stops within scheduled time still affect achievement. |
| Factory average | Sum of eligible actual packs / sum of eligible expected packs for the same completed clock hour. Missing, Not Scheduled, idle and unaccounted periods are excluded. Previous-hour comparison is shown only for the same eligible lines. |
| Current line state | Explicit line stops, planned stops and unresolved production faults take precedence. An active run alone is shown as unconfirmed; recent positive production is labelled Running at last report. No PLC telemetry is implied. |
| Pallets remaining | Existing reconciled run progress: `pallets_remaining`, `total_pallets_completed`, original `starting_pallets_remaining`. It is current-job progress, not an assumed future changeover. |
| Downtime today | Recorded intervals clipped to the factory day and scheduled coverage. Planned overlap takes precedence; overlapping unplanned faults count once. Changeover minutes are identifiable inside planned time. |
| Ongoing issues | Existing production and Engineering states remain independent. Ranked by active production impact then age; no severity is invented. Ticket age is not presented as measured downtime. |
| Breakdowns | Existing configured categories, with repair classification as fallback. Last seven days of unplanned stop minutes. Overlapping faults are allocated oldest-first, once. Each bar segment opens its contributing records. |
| Changeovers | Existing stop start, physical completion, workflow/QA state and Engineering request. The elapsed clock starts at the original stop, not Engineering acceptance. |

The full eight-hour series comes from the existing hourly reconciliation. Missing readings are gaps, not artificial zeros. Zero expected output is safe, and values above 100% remain visible with a review flag.

Thresholds default to red below 45%, amber below 65%, green from 65%. Optional deployment configuration: `PULSE_DASHBOARD_AMBER_PERCENT` and `PULSE_DASHBOARD_GREEN_PERCENT`, with validation `0 < amber < green <= 100`. There is no existing manager threshold editor to reuse, so none was invented.

The dashboard reads one Management-protected snapshot every 30 seconds after the preceding request completes. Hidden tabs skip polling; returning to the tab or reconnecting triggers a refresh. Superseded requests are aborted. Refresh failures retain the last snapshot and show a warning. A snapshot older than 90 seconds is marked stale. The latest production submission time is shown separately from refresh time.

## Database and API

New migration: `migrations/20261009131928_live_operations_targets.sql`.

It extends the existing target table with bounded notes, permits custom site-week start days while retaining Monday-only line targets, rejects overlapping site target weeks, enables RLS and revokes direct public/anon/authenticated access. No production records or existing tables are deleted. Target saves are audited and serialized with a transaction lock. Readiness now checks for the migration.

The migration was applied only to a disposable local PostgreSQL clone. It is deliberately not applied to live production. Future deployment must apply it before starting the new backend. Existing conflicting target weeks would cause the migration to fail atomically rather than silently rewrite targets.

New endpoints:

- `GET /api/v1/dashboard/live?week_start=YYYY-MM-DD`
- `POST /api/v1/management/live-weekly-target`

Both use the existing Management authentication dependency. The snapshot uses a fixed set of bulk queries in one repeatable-read, read-only transaction with a statement timeout; it does not request a separate endpoint for every widget.

This codebase has one factory per deployment/database. The permitted target scope is that existing factory; unknown sites and extra tenant identifiers are rejected. This is not a new shared-database multi-tenant model.

## Files added or modified for this task

Backend:

- `src/live_dashboard.py`, `src/live_dashboard_api.py`
- `src/api.py`, `src/database.py`
- `migrations/20261009131928_live_operations_targets.sql`
- `tests/test_live_dashboard.py`, `tests/test_dashboard_reports.py`
- `scripts/manual_integration/live_dashboard.py`
- `scripts/manual_integration/live_dashboard_fixtures.py`
- `scripts/manual_integration/live_dashboard_screenshots.py`

Frontend:

- `frontend/src/features/dashboard/LiveOperations.tsx`, `LiveOperations.test.tsx`, `liveTypes.ts`, `live-operations.css`, `api.ts`
- `frontend/src/features/dashboard/ProductionDashboard.tsx`, `ProductionDashboard.test.tsx`, `DashboardPages.test.tsx`
- `frontend/src/features/dashboard/engineering/EngineeringDashboard.tsx`
- `frontend/src/features/management/WeeklyTargets.tsx`, `ManagementHome.tsx`, `ManagementSession.test.tsx`
- `frontend/src/features/management/RequireManagementSession.tsx`, `destinations.ts`, `destinations.test.ts`
- `frontend/src/pages/DashboardPage.tsx`, `frontend/src/routes/AppRoutes.tsx`
- `frontend/live-preview.html`, `frontend/preview/live.tsx`, `frontend/preview/live-fixtures.json`

Protected navigation now retains line/fault/report query parameters through sign-in. Known-path validation is retained. Existing report tests still exercise the original detailed report, and the new dashboard has separate tests.

Earlier LineTech machine/fault preset changes already in this checkout are not part of this dashboard file list.

## Verification results

- Backend full suite: 1,134 passed, including 28 dashboard-specific checks and an authenticated response-model check.
- Frontend full suite: 557 passed across 44 files, including 14 new live dashboard/target tests.
- TypeScript type check and production build: passed.
- ESLint: passed with no warnings.
- `git diff --check`: passed.
- Local PostgreSQL rehearsal: passed. Applied migration, wrote a real hourly HMI update, verified 3,000 packs / 3 tonnes / 7 pallets remaining, saved an audited 6-tonne target and verified 50% progress, rejected an overlapping week, checked RLS, then dropped only the disposable local test database.
- Browser verification in headless Edge: no page errors or horizontal overflow at any requested viewport. Desktop normal state fits in 1920 x 1080. Smaller viewports scroll vertically.
- Visual states captured: normal, empty, missing hourly update, above target, Not Scheduled, disconnected/stale.
- Regression suites cover existing HMI, Engineering, Management, authentication and production calculations. They were not replaced with screenshot-only checks.

Vite emits a bundle-size advisory for the existing single-bundle architecture (about 571 kB minified / 163 kB gzip). Backend tests emit two upstream deprecation warnings. Neither fails the build/tests. Production-scale load and physical tablet touch interaction were not benchmarked in this task.

## Review screenshots

The screenshots contain clearly labelled synthetic records. Their figures are generated through the actual backend calculation layer. The local preview entry is not included in the production Vite entry build and rejects non-localhost access.

- [Desktop 1920 x 1080](live-dashboard-preview/desktop-1920.png)
- [Laptop 1440 x 900](live-dashboard-preview/laptop-1440.png) | [full page](live-dashboard-preview/laptop-1440-full.png)
- [Tablet landscape 1180 x 820](live-dashboard-preview/tablet-landscape.png) | [full page](live-dashboard-preview/tablet-landscape-full.png)
- [Tablet portrait 820 x 1180](live-dashboard-preview/tablet-portrait.png) | [full page](live-dashboard-preview/tablet-portrait-full.png)
- [Missing update](live-dashboard-preview/state-missing.png), [above target](live-dashboard-preview/state-above.png), [Not Scheduled](live-dashboard-preview/state-unscheduled.png), [empty](live-dashboard-preview/state-empty.png), [stale](live-dashboard-preview/state-stale.png)
- [Browser measurements](live-dashboard-preview/verification.json)

Interactive local preview: http://127.0.0.1:5178/live-preview.html while Vite is running.

## Remaining review and deployment conditions

This is technically ready for visual review and a staged deployment rehearsal, not an assertion that the live trial has already been validated.

1. Approve the layout. An approved visual mock-up was not supplied, so exact matching cannot be confirmed.
2. After approval, review the migration against a fresh backup of the deployment database and apply it through the normal release process. Do not deploy this branch without the migration.
3. Enter the real weekly target. Cross-check one real hourly submission, a fault closure and a changeover against HMI/Engineering after staging.
4. Confirm physical tablet readability/touch behaviour and production-scale query performance.

Completion-time estimates deliberately remain unavailable: the current records do not establish a reliable future-job plan/rate. Recorded HMI activity is periodic, not live machine telemetry. Legacy detailed reporting retains its explicitly labelled Monday reporting windows; the new configurable site week is displayed in Live Operations. Comparisons must use matching windows.

Stop here for visual approval. Nothing has been committed, pushed, merged or deployed for this task.
