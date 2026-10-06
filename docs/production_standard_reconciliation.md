# Fixed production standard and reconciliation

Local implementation, October 2026. No production migration or historical backfill has been applied.

## Definitions

- Management alone configures the baseline in Production standards. Versions match line, product, nominal pack weight, pack format, packs/case and cases/pallet. Product/format matching ignores case and surrounding whitespace. Customer is not part of this configuration key.
- Each version records manager identity from the authenticated management session, reason, effective time and server recording time. Versions are append-only. At Start Run the database selects the latest effective version at `started_at` (highest ID breaks equal effective times), snapshots its rate and records its version ID. Future versions are not selected early. A retrospective version applies only to subsequent run starts; existing snapshots never change.
- An applicable standard is required before a new run can start. Legacy technician `target_speed_ppm` input is accepted for request compatibility but ignored. New HMI requests omit it. The management version supplies both the legacy target field and the immutable standard snapshot.

- Actual: reported palletised production. Decimal pallets convert through packs/case and cases/pallet. Nominal tonnes = packs x configured nominal kg / 1000. Neither dispatch nor independently verified quality nor measured weight is claimed.
- Target = standard x scheduled minutes, clipped to run/product/clock-hour boundaries. Planned stops stay in target. Explicit Not scheduled time between runs is excluded.
- Signed variance = actual minus target. Shortfall = max(target - actual, 0). Overproduction = max(actual - target, 0).
- Recorded planned/unplanned minutes are interval unions, clipped to the reporting window. Planned takes precedence over overlapping faults. Carried faults are selected by line, not only their originating run.
- Raw stop equivalents = standard x unioned stop minutes. These are output models, not confirmed causal losses.
- Operating-speed reports are context only. No speed deficit is calculated or allocated. A report may suggest an explanation while the gap remains quantitatively unaccounted.
- Allocation caps each run/hour contribution to the observed shortfall in this order: planned, unplanned. This is an accounting convention, not responsibility or root cause.
- Remaining gap = max(shortfall - raw planned - raw unplanned, 0).
- Equivalent minutes = remaining packs / standard. Review at >=10 before rounding. These are not measured downtime or material dwell.
- Excess = max(raw contributions - shortfall, 0), retained as a reconciliation limitation.
- Notes are reported explanations, never quantified loss evidence.

## Calculation paths

`pulse_calculations.reconcile_production` is the authority. `database._review_period` selects the tablet/save evidence; hourly reports and dashboard attribution call the same pure function. `attribute_run_gap` now adapts the shared per-period result to existing dashboard bucket names. `other_or_speed_loss` remains an API compatibility key but is always zero; it does not represent an allocation.

Dashboard totals aggregate per-run clock-hour periods, retaining shortfalls and overproduction separately across product boundaries. Net variance uses comparable target and actual totals. Missing completed readings and unknown standards are excluded from comparable totals and explicitly included in coverage limitations. Actual legacy palletised output is retained separately and continues to count toward weekly produced-tonnage targets. Between-run stops use the outgoing agreed standard and configuration, not an operating setting.

Reports attach append-only operating evidence to each relevant period. Operating reports and corrections never change reconciliation figures. Stored hourly target values remain unchanged because operating settings do not change targets. Response formatting alone rounds Decimal arithmetic.

## Operating records and corrections

`POST /runs/{id}/operating-speed` requires new_operating_speed_ppm (>=0), reason, and reporting technician. effective_at defaults to submission time; an explicit timezone-aware retrospective time must be inside the run and no later than submission. Completed-run corrections are supported by this API. HMI has no authenticated person today: the validated technician is stored without claiming authenticated identity.

Each row retains previous best-known setting at that effective instant (nullable when unknown), effective_at, submitted_at, reporter, reason and optional supersedes_id. Corrections append a row; originals cannot be updated/deleted. One correction per superseded row; corrections may themselves be corrected. Same-effective-time records use increasing record ID deterministically. Later retrospective entries do not rewrite historical previous-setting snapshots; the effective timeline is rebuilt from current unsuperseded evidence.

The tablet uses visible controls for settings and corrections, with a device-local datetime input converted to timezone-aware ISO. History displays effective and submission times. A reason is required again for a correction.

Old `/target-speed` writes are explicitly refused with 409. Old queued tablet requests are not reinterpreted; users must review/discard them. New operating writes retain exact payload/key retry protection and run-row locking.

## Final reading

Completion preview reviews the final partial interval with the same authority. Completion saves and recalculates under its existing transaction/run lock. The confirmed save time is authoritative; preview time can be slightly earlier. The final response includes `xray.loss_review`. Cause unknown is allowed. An explicit No production answer records zero for an elapsed final interval; it does not turn other missing hours into zero. The unique (run, hour) constraint and idempotency prevent duplicate hourly/final writes.

## Migration and compatibility

Apply `20261005054638_fixed_production_standard.sql` only through a separately approved release, after existing migrations. It adds a nullable standard and the append-only operating evidence table, index, RLS, browser-role revocations and immutable-standard/evidence triggers. The migration was named by the cached Supabase CLI. Rehearsal uses standalone local PostgreSQL, not a linked Supabase project.

There is deliberately no automatic backfill. All pre-migration runs have unknown agreed standards, including runs with a historical target but no proof that it was the agreed configuration standard. Old `run_target_speed_changes` rows and stored hourly targets are retained. Legacy capture can finish using its historical target accounting, but the new reconciliation explicitly refuses to assert a fixed standard. Legacy between-run references are unknown and surfaced as such. A reviewed, evidence-backed backfill would require its own audited migration and deliberate handling of the immutable-standard trigger.

Historical actual counts, fault links, restoration timestamps, separate production/Engineering status and idempotency keys are unchanged. Mechanical remains the displayed repair classification; the legacy JSON key physical_component_failure is retained only for compatibility, not a causal assertion.

The old terminal session is disabled explicitly. Its helper code remains for historical reference/imported factory configuration. The old variable-target loss helper has no active application caller.

## Hypothetical tablet-to-dashboard demonstration

Management standard: 130 packs/minute. Scheduled interval: 60 minutes. Expected output: 7,800 packs. Reported actual output: 6,600 packs. Recorded stop: two minutes. Stop equivalent: 260 packs. Remaining unaccounted gap: 940 packs, or 940 / 130 equivalent production minutes. A technician reports reducing the machine to 110 packs/minute. This report remains visible with its effective time, reason, identity and audit history. None of the calculation figures changes. A possible explanation has been reported; it is not quantified evidence.

In another hour, report 3 pallets with a two-minute recorded stop . Target is 6,000, actual 3,000, stop equivalent 200, remaining gap 2,800 = 28 equivalent minutes. Entering unknown retains that gap. It does not create an Engineering cause or another downtime event.

An hour 500 packs short followed by an hour 500 packs over yields zero net variance, 500 positive shortfall and 500 overproduction. The earlier gap remains visible.

## Limits

Operating settings describe machine settings, not measured throughput. Stop equivalents can exceed observed shortfall; this needs review, not automatic causal attribution. Missing/legacy standards remain visible limitations. Missing operating reports do not reduce calculation coverage. Physical tablet usability and live rollout are not verified by local automated tests. No cost accounting, dwell tracking, dispatch capture or new cause/action-verification model was added.


## Local validation evidence

The operating-context correction is covered by regression tests for the 130/110 example, zero and above-standard settings, retrospective corrections, unknown causes and overlapping stops. Current validation results are reported with the change; older validation counts do not describe this revision.

Local checks for this correction: 645 backend regression tests and 82 synthetic PostgreSQL checks passed. No production data, production migration or deployment was used. Management-only configuration is now implemented for new runs only.

## Management workflow and release dependency

Management > Production standards creates a version and displays history. POST `/api/v1/management/production-standards` requires management authentication and an Idempotency-Key; GET on the same path returns protected history. The reason and manager are retained on the immutable version itself, in the same transaction. Retrying identical input/key returns the original version. POST `/api/v1/production-standards/resolve` is a read-only HMI preview; the database checks again when a run actually starts.

Local migration `20261005135527_management_production_standards.sql` follows the fixed-standard migration. It adds the protected version table and run foreign key, selects standards on INSERT, and protects historical snapshots on UPDATE. No versions or historical standards are invented or backfilled. Configure standards through management before new production starts after a separately authorised release. Active and completed pre-migration runs retain existing snapshots, including unknown standards.

## Management workflow validation

Local validation: 708 backend regression tests, 286 HMI/management/route tests and 94 synthetic PostgreSQL checks passed. The final response-field checks (136 tests), TypeScript, changed-component ESLint and Vite build passed. PostgreSQL checks exercised management authentication, identity, exact retry replay, technician override rejection, effective-time boundaries, future versions, missing configurations and immutable active/completed run snapshots. Two existing backend dependency deprecation warnings remain. No production migration or deployment was performed.
