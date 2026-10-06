## Dashboard review corrections - 2026-10-05

Implemented locally: incomplete reporting prevents green line status (open faults and red performance remain red); page Refresh includes hourly output; hourly and weekly panels disclose refresh failures while retaining last loaded figures; net output shortfall is distinguished from summed period shortfalls; line cards preserve reported legacy output when no standard comparison is available; filter guidance now describes summary scope accurately.

Regression checks cover missing coverage, unknown standards, complete green results, hourly refresh and legacy output display. Physical tablet/browser visual review remains outstanding. No production migrations or deployment are required by these changes.

# Rovema MVP snagging

## Current Management review ? 2026-10-05

This status supersedes older counts and open items later in this historical log.

Completed locally in this pass:
- Technician reporting now uses shared fixed-standard reconciliation, not stored legacy hourly targets. Nominal-tonne achievement compares like units across pack configurations. Positive period shortfalls are retained separately from later overproduction.
- Production stop intervals are clipped to selected runs, unioned and given planned-stop precedence. Carried faults are included by line. Engineering closure does not extend production downtime.
- Missing timed readings, unknown historical standards, invalid/overlapping reporting periods and incomplete coverage prevent ranking. Reported nominal output remains available separately. These figures are run-associated production evidence, not a skills rating or proof of responsibility.
- Performance dates select completed runs by London start date and include those runs in full; named period dates also use London time.
- Force-close and its authenticated manager/reason/before-and-after audit entry now commit in one transaction. Audit failure rolls back closure. Existing response-loss guidance still tells managers to refresh and check. Factory line/machine/button changes and weekly-target writes now also require their audit entries in the same transaction; configuration updates lock their before-state and weekly-target batches serialize by week.
- Dashboard filter scopes are explicit. Engineering summaries distinguish production status/downtime from Engineering work, and identify additive fault minutes that may overlap. Missing-feature cards no longer expose endpoint implementation instructions.

Validation for this pass: 722 backend regression tests, 177 affected dashboard/Management/performance UI tests and 101 fresh synthetic PostgreSQL/API checks passed. The database checks include deliberately failed audits proving rollback of run closure and configuration changes. Existing dependency/polling-test warnings remain. This is local software evidence, not a physical tablet or live deployment sign-off.

Still open:
- Decide whether editable Factory setup and weekly-target screens are required for MVP. Their existing APIs now have transactional audit protection; the screens remain unimplemented.
- Skills matrix: six agreed skills are Film change, Label change, X-ray (CCP), Casepacker, Robot Palletiser and Changeover. Rating definitions and assessment permissions remain unconfirmed; no automatic competence rating from downtime.
- Physical tablet/network walkthrough; production access controls; release backup/restore and rollback review. No deployment or live data/configuration change is authorised by this review.
- Casepacker cancellation and a dedicated historical changeover browser remain outside the current agreed MVP.



Local work only. No deployment approval, live configuration changes or live data cleanup. Checked items below mean implemented and tested offline. Production restoration and Engineering separation also passed a fresh local PostgreSQL rehearsal on 2026-10-02. Physical-tablet verification remains outstanding.

## Line technician

- [x] Start Run: reject fractional counts before confirmation, matching the existing API. Decimal target speeds remain valid.
- [x] Report to Engineer: allow an unlisted machine or section with a name and written details.
- [x] Report to Engineer: allow an unlisted reason alongside configured presets. Preserve the configured machine ID and require details.
- [x] Hourly report: expose the existing `other_loss_reason` field. Keep it available when a stop is recorded; include it in the pending-write identity.
- [x] Unplanned downtime: technician can select Resolved with details or Call Engineer.
- [x] Production restart: record the actual restart separately from engineering closure, as approved by the user.
- [x] Retrospective downtime: capture actual start/end times rather than treating the reporting time as the event time.
- [x] Hourly fault verification: confirm the actual restart time without extending downtime to the reporting hour.
- [x] Unexplained loss: hourly Save now reviews the residual gap after recorded stops, including carried faults from other runs on the same line. Prompt at 10 equivalent minutes or more; ask for a reason or explicitly save with cause unknown. Intervals are clipped/merged once, stop equivalents and equivalent minutes use the preserved management standard. Review is read-only; no invented downtime is saved. The tablet hourly and final partial readings use the shared reconciliation. Operating reports provide context only and do not allocate loss.
- [x] Casepacker changeover: explicit Yes/No choice; Yes requires requested format/program details and creates a linked Engineering request atomically with the line changeover. The next run is blocked until the accepting engineer marks the casepacker ready. No duplicate breakdown interval.
- [x] SBS presets recovered from user paper-sheet photos; confirmed BV1/BV2 belong to SBS and shared faults have their own equipment record. Button hierarchy implemented and rehearsed locally.
- [x] Casepacker: nine exact labels confirmed by the user, configured locally and tested through the real API/database.
- [x] X-ray/checkweigher and Robot presets configured and verified locally; running preview not yet updated.
- [x] Automated refresh/reconnection checks: replay saved hourly values/reasons, target changes, planned-stop actions, legacy changeover actions, End Run and fault reports using the original key. An uncertain response no longer claims nothing was saved.
- [x] Rovema-only configuration default, dry-run rollback, other-line preservation and active preset-button protection rehearsed on fresh synthetic PostgreSQL.
- [ ] Physical tablet check. Automated browser/component tests are not a factory-device sign-off.

## Engineering

- [x] User confirmed: production restart stops downtime; Engineering continues and closes separately.
- [x] Implement that decision consistently in API guards, database updates, queue filters, detail actions and reporting.
- [x] Prevent later engineering actions from overwriting the production restoration time.
- [x] Add linked casepacker changeover acceptance, updates and explicit readiness confirmation, with authenticated actors, durable retry keys and history.
- [x] Rehearse restart, Engineering updates/closure/handover, retry protection and two competing restart confirmations against fresh local PostgreSQL. Broader concurrency scenarios remain part of final regression testing.

Engineering actions and queues now use engineering status. Closure writes its own Resolution history timestamp and does not write production status or `resolved_at`. Production restart records the actual time plus technician, details and reporting time in the existing audit table (action `hmi_production_restored`, actor role `line_technician`). Technician-resolved stops retain their actor/details in the fault record, set `engineer_called=false`, and stay out of Engineering jobs. No new schema migration is needed for these changes. Historical records are not rewritten.

## Management

- [x] Remove the false assurance that nothing changed after an uncertain force-close response. Tell the manager to refresh and check the run status.
- [x] Confirm management reporting distinguishes production downtime from Engineering work time; no labour-time calculation is claimed.
- [ ] Agree whether machine/preset editing in Factory setup is required for the MVP; it is currently a placeholder, with configuration available through the API/script.
- [x] Review dashboard calculations and audit records against the final workflows; fixes and remaining scope decisions are listed in the current review above.

## Verification so far

- Latest HMI and Engineering regression tests: 245 passed.
- Previous Engineering and Management frontend baseline: 154 passed. Existing Engineering polling tests emit React `act` warnings.
- TypeScript compilation, lint of the edited frontend files and the Vite production build passed.
- Latest backend regression run: 459 passed with real database connections explicitly blocked. Tests use mocked APIs and scripted database cursors. These results do not demonstrate real database persistence or physical tablet operation.

## Deployment gate

Still pending: workflow completion, migration rehearsal, HMI access controls, Hostinger configuration, backup/restore and rollback review, and a real Rovema tablet pilot. Live GIC run/stale-fault cleanup is separate and has not been performed in this work.

Preview blocker resolved on 2026-10-02: recovered PostgreSQL 17.6 and the schema-only export from Claude's local scratchpad. Created a fresh cluster under `C:/Users/KuriraiMahamba/Documents/Codex/2026-09-30/ca/work/pulse-db-rehearsal/data`, listening only on 127.0.0.1:65439. Rehearsal uses a new uniquely named database on every run, the recovered schema plus migration 0004, and synthetic records only. No live connection or data was used.

12 real API/database checks passed, including 10-minute downtime remaining 10 minutes after late confirmation and Engineering closure, one audit entry after retries, technician-resolved stops excluded from Engineering jobs, and two simultaneous restart confirmations producing one success and one conflict. Test runner and results: `C:/Users/KuriraiMahamba/Documents/Codex/2026-09-30/ca/work/pulse-db-rehearsal/rehearse.py` and `results.json`. This is a test of the current backend against the recovered schema, not proof that live Supabase currently has the same schema or that a physical tablet works.

Reusable runner: C:/Users/KuriraiMahamba/Documents/Codex/2026-09-30/ca/work/pulse-db-rehearsal/run-test.ps1. Verified twice from fresh databases; all 12 checks passed each time. The runner starts its local cluster when needed and stops it afterwards. The test server is currently stopped, with results retained.

Latest line-tech loss-prompt verification: 176 HMI tests and 374 targeted backend tests passed. Local PostgreSQL rehearsal now passes 16 checks, including the two-minute stop leaving a 28-minute residual gap and overlapping stops being counted once. User confirmed that Engineering readiness must block the next run; implemented locally on 2026-10-03. The recovered reference documents contain examples but no complete approved Rovema preset list; do not invent preset reasons.


## Casepacker readiness verification - 2026-10-03

- Confirmed user rule: when a casepacker format/program change is requested, the next run must wait for Engineering readiness. Technician End Changeover and an Engineering progress update do not release this gate.
- 256 HMI/Engineering tests and 437 backend tests passed (352 workflow tests plus 85 run API tests). TypeScript, edited frontend lint and Vite build passed. Existing polling tests still emit React act warnings; dependency deprecation warnings also remain.
- Fresh synthetic local PostgreSQL rehearsal: 31 checks passed. Includes one request/history entry on retries, persisted readiness time, owner-only updates, unauthenticated rejection, start blocked after End Changeover, direct database start bypass rejected, next-run linkage, no duplicate fault interval and no-request changeover unchanged.
- New schema file: `migrations/20261002234341_casepacker_readiness.sql`, generated with the Supabase CLI and kept in the repository's existing migrations directory. Apply **after 0004** and before running the updated backend. It creates two backend-only RLS tables and readiness/line-stop guards. No schema changes were applied to live.
- Engineering shows requests until their next run starts. Their history remains stored and available through the linked stoppage status endpoint afterwards. This implements acceptance, updates and ready; reassignment/cancellation and a dedicated historical changeover browser are not added in this item.
- Physical tablet testing remains outstanding. This gate controls Pulse run recording; it is not a physical machine interlock.


## Remaining line-tech snagging - 2026-10-03

Scope remains line technician first, then Engineering, then Management. No deployment or live data/configuration changes are authorised by this stage.

### Completed in this pass

- `machine_dropdowns.sql` now defaults to Rovema. Each invocation targets exactly one known line; Guill/GIC require an explicit future scope. Unknown/all-line scope is rejected. Default is still a dry run. It refuses to hide a currently active machine carrying active preset buttons; review the approved mapping instead of silently dropping the technician's buttons.
- A lost reply or server failure is reported as an unconfirmed result, because the write may already have committed.
- Fault recovery shows the original machine, reason, reporter, notes and actual stop/restart times. Retry sends the stored payload and key without reconstructing it from current inputs. Rejected 4xx fault submissions return to correction; uncertain submissions retain the reminder.
- Check and retry on the active run now replays stored hourly readings/loss reasons, target changes, planned-stop actions, legacy changeover actions and End Run directly. This also works when the server state already reflects the action and the normal form would reject it as redundant.
- 189 HMI tests passed. Fresh synthetic database rehearsal passed 39 checks, including eight new configuration checks. No backend application code changed in this pass.

### Still needs evidence

- The full original approved Rovema fault-button list was not found in the local reference texts or checked preview seed files. Example reasons/test data are not approval. User has been asked where the source list is saved. Do not rename/copy presets by guessing, and do not mark this item complete.
- Physical tablet: on the isolated preview, confirm touch controls and text fit; refresh during a submitted fault/hourly reading; reconnect after a lost response and confirm a single saved entry; verify the casepacker gate updates after readiness; check tablet clock/timezone against the actual recorded stop times. Record device/browser and results before pilot sign-off.
- Run-linked saved actions have durable recovery. Start Run and between-run choices also recover authoritative state from Home and have database uniqueness guards; unsent form drafts are not guaranteed to survive closing the browser. Private browsing/blocked local storage reduces durable recovery to the current page session.


## SBS button hierarchy - 2026-10-04

User confirmed SBS > BV1 / BV2 / shared SBS equipment > section > fault. Machine and fault selection now use visible buttons. The new shared record is `SBS Shared Equipment`; existing `SBS Bagger BV1` and `SBS Bagger BV2` IDs remain separate. `machine_dropdowns.sql` now contains six Rovema records, superseding the earlier five-record list.

The paper sheet supplies eight bagger presets per BV: Film torn, Bag crosswise, Top seal, Vertical seal, Bottom seal, Label snapped, Bag printer and Ribbon tension. Shared SBS presets use the user's clarified meanings: SBS discharge belt jam, Secondary jaw cut-off extractor fault, Top fold guide fault. Film/label changes remain planned events; they are not duplicated as fault presets.

`rovema_sbs_presets.sql` adds missing presets on these three active Rovema equipment records only, after machine configuration. Dry run by default; audit actor required. Existing reasons/IDs are not renamed, moved or deleted, and repeat runs add no duplicate rows. Inactive/conflicting existing presets require review.

Navigation groupings are in `frontend/src/features/hmi/faultSections.ts`; the grouping is a UI implementation choice based on the supplied labels, not a new diagnosis. Unknown configured reasons remain available under Other faults. Other section and Other fault reason allow required written details. Reports retain machine ID and button ID; the section is saved in the note (not a new database column). Shared faults are rejected by the server if paired with a bagger's machine ID.

Physical process descriptions affected by speech transcription (air removal, sealing, extraction and transfer details) are not encoded as technical facts. This change implements the confirmed reporting hierarchy, not a simulation of the equipment. No live configuration/data changes or deployment.


## Casepacker presets - 2026-10-04

User confirmed: Magazine pull error; Product positioning; Infeed jam; Cycle-chain overload; Main discharge conveyor; Pusher limit position; Gluing issues; Printer; Purge printer. These supersede the earlier photo transcriptions "Infeed position" and "Cross-chain overload".

`scripts/production_config/rovema_casepacker_presets.sql` configures these nine fault buttons against the active Rovema Casepacker only. Uses the existing visible-button UI and Other with required written details. No new frontend code or database schema required. Dry run is the default; explicit commit and named audit actor are required. Existing buttons/history are not renamed or deleted. Unknown existing presets remain for separate review.

Fresh synthetic PostgreSQL rehearsal: 49 checks passed, including dry-run rollback, all nine names/order, preservation of existing buttons, repeat-apply idempotence and each of the nine presets saved via the fault-report API against the correct Casepacker ID. No live configuration/data change or deployment.


## X-ray and Robot palletiser presets - 2026-10-04

`scripts/production_config/rovema_xray_robot_presets.sql` adds the supplied paper-sheet fault presets on Rovema only. X-ray / Checkweigher: Machine jam; CCP check fail. Robot Palletiser: Pallet stacker fault; Pallet outfeed transfer error; Infeed conveyor not moving; Incorrect stacking; Dropping cases; Safety sensor alarm; Pallet position; Wrapper.

Uses the existing visible fault buttons and Other fault reason with required details. Routine test-kit/hourly/end-of-shift checks remain in the planned check workflow, not fault presets. Apply machine_dropdowns.sql first. Dry run by default; explicit commit and named audit actor required. Existing buttons and history are preserved; inactive or differently classified matching presets stop the transaction for review.

Verified with a fresh synthetic PostgreSQL database: 57 checks passed. All ten presets saved through the actual fault-report API against their correct machines; mismatched Casepacker identity was rejected. Dry run rolled back, existing buttons were unchanged and repeat application added no buttons or audit rows. This verifies local configuration and API behavior, not a physical tablet or live deployment. The configuration has not been applied to live or the existing running preview.


## Engineering review - 2026-10-04

Reviewed the React workspace, job detail, fault cards, polling, Engineering API and database ownership guards, plus casepacker queue/API/history. No live connection or deployment.

Completed:
- Technician report_note was stored but omitted from Engineering's query, API model and detail panel. It now appears as Technician report, preserving SBS section/details and line breaks; legacy null notes render no empty section.
- Corrected the closure screen's obsolete statement that it restores production. Closure remains Engineering-only. Detail duration is now explicitly labelled Production downtime.
- Repair updates losing an ownership/status race now return 409 with a refresh instruction, rather than a misleading database-error 503. The guarded insert still writes nothing after handover/closure.
- User approved casepacker shift handover with a required note. Current owner can confirm handover, releasing ownership atomically with the history entry. Next run stays blocked; another engineer must accept before updates/readiness. Idempotent retry cannot release the new owner's assignment.
- New additive migration: migrations/20261004092500_casepacker_handover.sql, after casepacker_readiness. Adds handover to the existing history action constraint and requires a nonblank handover note. Existing RLS/grants remain unchanged. Rehearsed on fresh synthetic PostgreSQL; not applied to live or existing preview.

Verified: 108 targeted backend tests, 77 Engineering component tests, TypeScript compilation, and 62 synthetic database/API checks passed. Component polling act warnings and Python dependency deprecation warnings remain. The database checks include technician notes reaching Engineering, owner-only handover, next-run blocking, retry preservation of the next owner and independent production restoration/Engineering closure. These are not physical-device sign-off.

Remaining Engineering snags identified by code review:
- Ordinary fault repair updates have no durable idempotency key. A lost response followed by retry can add duplicate history. Close/handover have state guards, but their response-loss recovery still needs explicit UI reconciliation. This must be corrected before Engineering sign-off.
- Casepacker pending action keys live only in a component ref. Refresh/sign-out loses them. Polling can replace controls after an uncertain accept/ready/handover, leaving no obvious retry path. Persist/reconcile pending actions and freeze the original payload until confirmed.
- Casepacker refresh requests can overlap and render out of order. Add the same latest-request protection used by ordinary fault polling.
- Unsaved Engineering drafts are lost on refresh/sign-out; confirm intended MVP behavior or retain drafts safely.
- Exercise simultaneous accept, update/close and handover actions with separate clients; current regression proves guarded conflicts and restart concurrency but does not cover every interleaving.
- Real-device walkthrough remains required. Casepacker cancellation and a dedicated historical changeover browser remain outside the current implementation.

Review outcome: core workflows verified locally, but Engineering is not signed off until response-loss/retry recovery is corrected and tested. Management review remains next after Engineering snagging.


## Engineering recovery and concurrency completed - 2026-10-04

This section supersedes the response-loss, draft and concurrency snags recorded in the preceding Engineering review.

- [x] Fault Accept, Add Repair Update, Close and Hand Over now send durable idempotency keys from the tablet UI. The keyed API path claims/replays before checking current job ownership, locks the job row, writes its history/state and stores the response in the same transaction. Production restoration remains independent. Existing no-key API callers retain the legacy contract; external callers must send keys to receive retry protection.
- [x] Both fault and casepacker actions retain the original payload/key in browser storage, scoped to the signed-in engineer. A recovery panel outside job cards remains visible after polling removes a job or its action controls. Refresh/sign-out requires login again but retains pending work for that engineer; no tokens are stored. Conflicts allow correction; connection errors and expired sessions retain recovery. New writes are refused if durable storage cannot be saved. Pending actions older than 89 days require history review instead of risking the server's 90-day replay-expiry boundary.
- [x] Repair, closure, handover and casepacker note drafts survive closing/reopening and refresh in the same browser. Confirmed actions clear their corresponding draft. Unsent draft persistence is best-effort if browser storage is disabled; submitted actions require working storage. Browser-data deletion or switching devices does not transfer drafts.
- [x] Casepacker polling aborts superseded reads and ignores late responses; manual refresh is covered too. Unmount aborts active reads.
- [x] Fresh synthetic PostgreSQL tests with separate concurrent HTTP clients: two engineers accepting yield one owner; two identical repair retries yield one history row and equal responses; changed-payload retry is rejected; update versus close and update versus handover serialize safely; closure retry preserves production time; old handover retry cannot release a new owner.
- [x] Browser rendering checked in Chrome with synthetic fetch responses, no backend connection, at 1280x800 and 800x1280. No horizontal overflow; technician report and production/Engineering status remain readable. A typed repair draft survived an actual browser refresh. Temporary fixture/server/tab removed after review.
- [ ] Physical Rovema tablet and factory network pilot: still required. Browser viewport emulation is not physical-device approval.

Final validation for this pass: 279 HMI/Engineering component tests (including 87 Engineering tests), 112 targeted backend tests, 69 fresh synthetic PostgreSQL/API checks; TypeScript, lint on edited modules, Vite production build and targeted git diff whitespace check passed. Existing React polling-test act warnings and Python dependency deprecation warnings remain. No commit, push, live data/configuration change or deployment.

Engineering software snags from this review are addressed locally. Next: physical-device verification and Management review. Casepacker cancellation and a dedicated historical changeover browser remain outside the agreed MVP scope, not newly implemented features.


## Release snag resolution ? 6 October 2026

This section supersedes earlier open software snags addressed below. Changes are local; no production data, migration or deployment was used.

- Shared product/customer/shift catalogue now drives HMI and dashboard choices. Historical spelling aliases remain readable and filter correctly; historical rows are not rewritten. Product aliases also resolve Management standards.
- Tablet capture requires server-validated device access. Missing/expired sessions cannot write; Management and Engineering remain separate roles. Reported operator names are not individual identity authentication. Tablet sessions expire after 12 hours or logout; one worker/replica is required.
- Management standard submissions preserve original payload, manager and idempotency key across refresh and uncertain responses. Existing run standards/effective history remain protected. Operating-speed reports remain contextual and allocate no loss.
- All seven Rovema tasks have an independent completed-task observation form. It records performer, start/end, product, from/to configuration, waiting, shared work, completion and notes. Durable retry keys prevent duplicate writes. This form never creates production downtime.
- Management Performance shows evidence plus fastest/median/slowest by reported comparable transition. Zero/open timers, missing context, waiting, shared work, unsuccessful work and legacy unconfirmed observations are excluded from benchmarks but remain visible. No automatic ratings or competence claims; all cells remain grey.
- Additive task-observation migration protects evidence from overwrite and denies direct anon/authenticated access. Readiness now checks through this migration, including casepacker and both standard migrations.
- Production entry point `python -m src.serve` enforces distinct non-placeholder secrets and one worker. Deployment, backup/restore, rollback and physical acceptance steps are in `docs/deployment_release_gate.md`.

Validation: 1,073 backend tests, 487 frontend tests, 115 synthetic PostgreSQL/API checks, TypeScript, ESLint and production build passed. Synthetic checks cover all seven task writes/replays, duplicate conflicts, no extra stops, evidence immutability, client-role denial, catalogue aliases and current readiness, alongside existing production/Engineering/Management concurrency and audit tests.

Non-blocking tool warnings: two Python dependency deprecations, existing React test act warnings, and the frontend bundle exceeds Vite's 500 kB warning threshold (about 145 kB gzip). No physical tablet sign-off or production backup verification is claimed.

Remaining release gates: approve the actual hosting/secret configuration, verify a recoverable production backup and rollback artefact, apply reviewed unapplied migrations during the authorised release, configure approved standards, and complete the Rovema tablet/factory-network walkthrough. These are deployment/operational checks, not completed local software work.
