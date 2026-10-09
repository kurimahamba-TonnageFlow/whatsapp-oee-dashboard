# LineTech preview

Specification: Pulse_LineTech_Complete_Implementation_Prompt.pdf, supplied 9 October 2026.

## Inspection and scope

Reuse React HMI, Management authentication, FastAPI capture routes, `production_lines`, `machines`, `buttons`, `downtime_events`, `line_stoppages`, `changeovers`, `casepacker_requests` and their idempotency/Engineering action history. Keep production calculations unchanged.

The existing Engineering changeover request is named Casepacker internally. Extend its linked context rather than introducing a competing job system. Production stop, Engineering response/work, verification and restart remain independent times.

LineTech configuration is additive and opt-in per line. Existing installations and historical records retain their original machine/button IDs and behaviour. Configuration changes use Management authentication and the existing audit log.

The repository has confirmed SBS, Casepacker, X-ray and Robot presets. The original paper sheets are not attached. Preserve those confirmed labels; do not silently replace them with unverified candidate labels from the PDF.

There is a QA reporting view but no dedicated first-off/CCP approval application. Record changeover verification explicitly, without treating Engineering completion or a routine CCP stop as a passed check. A dedicated QA permissions/sign-off workflow remains a separately scoped decision.

All implementation and verification take place in the isolated `feature/linetech-preview` worktree. The user approved commit, GitHub push and deployment on 9 October 2026 after preview review. Deployment still requires the backup, migration and health checks below.

## Implemented

- Three prominent stop actions using existing Pulse colour tokens: planned green, unplanned amber, changeover blue. Existing hourly capture and End Run remain available.
- Four configurable machine groups. Existing machine and button IDs remain authoritative. SBS chooses BV1/BV2/shared equipment once, then category and fault. Other Fault requires one short description. Presets do not require typing.
- Film and Label changes capture their component; CCP downtime never implies a passed check. The existing start/end transaction and timer remain in use.
- LineTech repair can be saved either with confirmed production restart or while production is still stopped. The latter records a repair timestamp, keeps production downtime open and creates no Engineering call.
- Product, Format and Size changeovers use End Run → existing line stoppage → existing changeover record. Format/Size create exactly one existing Engineering request. Product Engineering involvement is configurable.
- Engineering response uses the first acceptance. Work duration sums accepted intervals and excludes waiting between handovers. Neither is added to the production-stop duration.
- Physical completion, recorded QA verification and actual new-run start are separate. A database guard rejects restart before verification or with a configuration that differs from the selected changeover.
- Cancellation records who/when/why, cancels the linked Engineering request, and preserves the production-stop clock until a deliberate new run starts.
- Management Factory Setup now edits navigation, categories, planned components, products, sizes and formats. Existing CRUD endpoints handle machine/fault additions, names, order and active state. Configuration uses the existing audit log.
- QA reporting shows recorded type, verification identity/reference and cancellation. Legacy rows remain explicitly unclassified/unverified.
- Start Run uses configured LineTech choices and sends the selected stored format. Older run records can supply their existing pack type when their separate format field is absent.
- New optional fields do not invalidate the idempotency fingerprints of pre-upgrade tablet retries.

## Local review

Run `npm run dev -- --host 127.0.0.1 --port 5178` from `frontend`, then open:

`http://127.0.0.1:5178/linetech-preview.html`

This separate preview entry uses the actual React screens with clearly labelled synthetic data. Its client replacements are confined to that entry. It makes no live API calls and is not included in the production build entry.

Use the scenario tabs to try:

1. Planned → Film Change → BV2 → Confirm → End.
2. Fault → SBS / Bagger → BV1 → Film → Film Torn → Resolved by LineTech → confirm actual restart, or record that restart is still pending.
3. Fault → Case Packer → Faults → Infeed jam → Report to Engineer.
4. Changeover → Product/Format/Size → configured value → Confirm. For Format/Size, switch to Engineering, accept, enter work/settings and complete the work. Return to Stoppage, confirm physical completion, record actual verification and continue to new-run setup.
5. Management → edit the configuration. The preview's saves are synthetic; production uses the authenticated Management endpoints.

Screenshots are in [linetech-preview](linetech-preview/). Key comparisons:

- [Before: existing fault screen](linetech-preview/00-before-fault-screen.png)
- [After: main stop navigation](linetech-preview/01-active-run-landscape.png)
- [After: four machine groups](linetech-preview/02-fault-machines.png)
- [Engineering job](linetech-preview/08-format-engineering.png)
- [Verification](linetech-preview/09-verification.png)
- [Mobile](linetech-preview/11-mobile.png)
- [Management setup](linetech-preview/12-management-setup.png)

## Verification

- Backend suite: 1,101 passing tests.
- Frontend suite: 537 passing tests.
- TypeScript/Vite production build and ESLint checked. Vite retains its non-blocking bundle-size warning.
- Final migration applied to a fresh local PostgreSQL clone: all 11 schema-readiness checks pass; the guard remains security-invoker.
- `scripts/manual_integration/linetech_workflow.py` checks real local transactions: three changeover lifecycles, duplicate/replay protection, Engineering ownership and handover, physical/verification/restart guards, cancellation, all four Film/Label component choices, CCP stop, resolved/escalated faults, repair awaiting restart, configuration audit and preserved IDs.
- `scripts/manual_integration/linetech_visual.py` exercises the actual React screens with synthetic fixtures, captures the screenshots and checks for browser errors/horizontal overflow at 1280×900, 768×1024, 390×844 and 1440×900.
- Existing hourly calculations and Engineering fault classification/handover tests remain in the regression suites. An already-failing hourly-card test assertion was reproduced on the original branch and changed to assert the labelled figure instead of counting repeated text. No hourly calculation was changed.

## Main files

| Area | Files |
|---|---|
| Schema | `migrations/20261009110303_linetech_workflow.sql` |
| Backend | `src/linetech.py`, `src/linetech_api.py`, `src/database.py`, `src/api_idempotency.py`, `src/pulse_capture_api.py`, `src/hmi_config_api.py`, `src/api.py` |
| HMI | `frontend/src/features/hmi/screens/LineTech*`, existing Active Run/Planned/End Run/Start Run/Fault screens, `HmiScreen.tsx`, `linetech.ts`, `linetech.css`, shared API types |
| Engineering | `CasepackerQueue.tsx`, `casepackerApi.ts`, `changeoverTimes.ts` |
| Management / QA | `LineTechSetup.tsx`, Management routes/home/destinations, `QaDashboard.tsx`, dashboard types |
| Preview / tests | `frontend/preview/linetech.tsx`, `frontend/linetech-preview.html`, LineTech unit tests, regression assertions and the two manual-integration scripts |

## Go-live assessment

Preview reviewed and release authorised by the user on 9 October 2026. Live deployment is pending; this document does not assert that deployment or factory acceptance has completed.

Before release, confirm the actual per-line machine/category labels against the factory's sheets, populate valid sizes and formats, and agree who may record the QA reference. The QA form records the technician's confirmation of external first-off, label, date-code and CCP evidence. It is not a dedicated QA-authenticated sign-off system. No historical QA pass is inferred.

LineTech is disabled by default. After release approval, take a fresh production backup, apply the additive migration before deploying this backend/frontend, verify `/health/ready`, configure/review each line in Factory Setup and enable it deliberately. Refresh the tablets. Rehearse one real permitted changeover with the factory team before normal operation. Do not overwrite or reset existing trial/live records as part of this change.

The current stop's workflow marker, rather than the latest feature-toggle value, controls its completion screen. Disabling LineTech therefore does not strand an already-started structured changeover. Existing legacy changeovers keep their original completion screen.
