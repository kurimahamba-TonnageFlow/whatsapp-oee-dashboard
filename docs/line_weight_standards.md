# Line and pack weight standards

Management records line, pack weight (kg), speed (packs/min), effective local
 date/time and reason. Changed by is read-only and comes from the signed-in
management session. The server retains its separate recorded-at timestamp.

New standards cover every product, pack format and case/pallet configuration
for that line and weight. Expected packs use this standard; conversion to
cases and pallets still uses each run's actual pack configuration.

Existing configuration-specific versions remain unchanged. The newest effective
applicable version wins (effective time, then version ID), considering both
line/weight standards and matching legacy versions. Future versions do not apply
early. Existing runs retain their immutable speed/version snapshots. Technician
speed reports remain context only and never allocate the production gap.

Deployment requires migrations/20261008232014_line_weight_production_standards.sql
before deploying the new API. Back up and rehearse on a restored database first.
Applied to the production database on 9 October 2026 (UTC), after a fresh
backup and the isolated PostgreSQL rehearsal. Verified that existing runs and
standards were unchanged. It does not backfill or rewrite recorded output. Old clients submitting complete
configuration-specific versions remain supported, including pending retries.
