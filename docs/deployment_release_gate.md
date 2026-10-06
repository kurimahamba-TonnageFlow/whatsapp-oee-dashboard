# Release procedure ? 6 October 2026

Local software corrections are ready for validation. This file does not record a production deployment or physical-device approval.

## Release contents

Deploy the backend and frontend from the same reviewed revision. Include `src/production_catalogue.json`; both applications depend on it. Build frontend with a same-origin API (`VITE_API_BASE_URL` empty), serve `frontend/dist` behind HTTPS, and proxy `/api` and `/health` to the backend. Keep database credentials and all PINs server-only. Preserve SPA fallback for client routes.

Use `python -m src.serve` behind the reverse proxy. It validates distinct secrets (minimum 12 characters), refuses placeholder configuration and runs exactly one API worker. Run exactly one replica: Management, Engineering and tablet sessions and rate limits are process-local. A restart requires signing in again; pending submissions remain in browser storage. Do not enable horizontal scaling until session/rate-limit storage is shared. Restrict direct access to the backend loopback listener and configure trusted proxy handling for the actual hosting layout.

Set DATABASE_URL, MANAGEMENT_PIN, ENGINEERING_PIN and HMI_DEVICE_PIN through the host's secret configuration. Temporary local-preview PINs are not deployment credentials. If using separate origins, configure the exact HTTPS HMI_ORIGIN and DASHBOARD_ORIGIN and allow X-HMI-Session. Verify API connectivity on the factory network before capture begins.

## Database release gate

Before production changes, confirm the target project and migration history, take a recoverable backup and prove restoration into an isolated database. Retain the previous application artefact and record the cutover time. Local synthetic rehearsal is not proof of a production backup.

Apply only unapplied migrations, in order, after existing 0001?0003:

1. 0004_fixed_hour_reporting.sql
2. 20261002234341_casepacker_readiness.sql
3. 20261004092500_casepacker_handover.sql
4. 20261005054638_fixed_production_standard.sql
5. 20261005135527_management_production_standards.sql
6. 20261006021758_task_observations.sql

Do not run destructive down migrations. New schema and historical evidence must remain intact if the application release is rolled back. Pause writes first; only restore a backup after reconciling post-backup production records, otherwise valid factory evidence would be lost. Rehearse compatibility of the intended rollback artefact before cutover; do not assume an older app understands the new standard constraints.

Require `/health/ready` to return 200. It checks all listed schema generations. Check server logs without exposing credentials. Configuration SQL scripts remain dry-run-first and require a named audit actor; schema readiness does not prove machine presets or standards are configured.

Management must configure the approved standard for each required line/product/pack configuration before starting new runs. Effective versions apply to new runs; existing run snapshots remain immutable. Technician speed reports remain context only. Do not backfill legacy standards without evidence and a separately reviewed plan.

## Factory acceptance before opening capture

On the actual Rovema tablet and factory network, verify tablet sign-in, the complete technician/engineer rosters, customer/product/shift choices, run start, hourly entry, loss display, production restoration and separate Engineering closure. Test expired sessions and a lost-response retry. Confirm only Management can open Performance and standard configuration.

Record each of the seven task types, then verify it appears in Management > Performance. Confirm fastest/median/slowest group only comparable reported configurations; waiting/shared/incomplete/legacy observations remain visible but excluded. All ratings remain grey pending agreed benchmark rules. Task observations do not add downtime or allocate production loss.

Inspect portrait/landscape layout, keyboard entry, clock/timezone (Europe/London), Wi-Fi loss and refresh recovery. Record operator acceptance and rollback owner. These physical checks cannot be signed off by unit tests.
