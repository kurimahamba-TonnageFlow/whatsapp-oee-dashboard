# Operational Intelligence preview review

Status: implemented and validated locally. **Not committed, pushed, merged or deployed.**
Route: `/dashboard/operational-intelligence`. The separate Live Operations page remains unchanged.
No database migration, production data change, package dependency or financial record was introduced.

## Review the screen

Local synthetic preview: http://127.0.0.1:5178/intelligence-preview.html (requires the local Vite server).
The preview uses labelled synthetic production records passed through the real backend calculations; screenshots are not live factory results. Its mode controls demonstrate normal, empty, Not Scheduled and failed-refresh states. Production filters and refresh call the authenticated API in the application; the isolated visual fixture harness does not fetch a database.

- [Desktop 1920 x 1080](intelligence-preview/desktop-1920.png)
- [Laptop 1440 x 900](intelligence-preview/laptop-1440.png), [full page](intelligence-preview/laptop-1440-full.png)
- [Tablet landscape 1180 x 820](intelligence-preview/tablet-landscape.png), [full page](intelligence-preview/tablet-landscape-full.png)
- [Tablet portrait 820 x 1180](intelligence-preview/tablet-portrait.png), [full page](intelligence-preview/tablet-portrait-full.png)
- [Phase 2 explanation](intelligence-preview/phase-2-modal.png)
- [No production records](intelligence-preview/state-empty.png)
- [Not Scheduled](intelligence-preview/state-unscheduled.png)
- [Failed refresh](intelligence-preview/state-stale.png)

The visual structure follows the supplied reference: navy shell, five KPI cards, commercial preview, three insight panels, material flow, line snapshot and a downtime comparison. Existing navigation, branding font and session controls remain. The desktop presents the main dashboard together; laptop and tablet layouts scroll vertically and preserve every panel. No horizontal overflow or browser errors were detected at the four requested dimensions.

Deliberate differences from the reference: every financial amount is a rose Phase 2 placeholder; the donut shows an unclassified measured gap rather than unsupported recovery proportions; disconnected material stages show no invented tonnes. Faults and priorities come from actual records when used in the application, not the reference image's example events.

## Components and files

- `frontend/src/features/dashboard/intelligence/OperationalIntelligence.tsx`: rebuilt existing page, authenticated snapshot, filters, refresh, charts, real operational values and data notes.
- `frontend/src/features/dashboard/intelligence/Phase2FinancialMetric.tsx`: one reusable locked metric, chart trigger and modal provider. Every financial trigger opens the same explanation; native dialog supports keyboard dismissal, focus containment and focus return. Discuss Phase 2 shows a contact message because no approved enquiry route is configured.
- `frontend/src/features/dashboard/intelligence/operational-intelligence.css`: page-scoped navy styling and responsive layouts; shared shell changes apply only while this page is present.
- `frontend/src/features/dashboard/intelligence/types.ts` and `frontend/src/features/dashboard/api.ts`: typed snapshot contract and abortable API request.
- `src/operational_intelligence.py`: combines existing production readers/calculations with interval allocation and conservative evidence summaries.
- `src/intelligence_api.py`, registered in `src/api.py`: Management-protected production snapshot and server-side financial capability guard.
- `tests/test_operational_intelligence.py`, `tests/test_dashboard_reports.py`, `frontend/src/features/dashboard/intelligence/OperationalIntelligence.test.tsx`, and `frontend/src/features/dashboard/DashboardPages.test.tsx`: calculation, authorisation, interaction and regression coverage.
- `scripts/manual_integration/intelligence.py`: disposable local PostgreSQL clone, real HMI write and SQL-to-dashboard verification; never accepts a remote database URL.
- `scripts/manual_integration/intelligence_fixtures.py`, `intelligence_screenshots.py`, `frontend/intelligence-preview.html`, `frontend/preview/intelligence.tsx` and `intelligence-fixtures.json`: localhost-only synthetic visual harness and reproducible screenshot checks. Not production build entry points.

## Data and calculation boundaries

Weekly tonnes reuse historical run pack weight, packs per case and cases per pallet, multiplied by confirmed hourly pallets. Corrections are deduplicated by run/hour. Whole readings retain their recorded operational-shift membership, avoiding duplication across weeks. The configured site week and Europe/London timezone are reused; default is Monday 06:00. The weekly clock accounts for daylight-saving changes.

Site targets come from existing Management configuration; selecting a line uses its explicit line target if present. No site target is arbitrarily divided between lines. Missing quantities or targets stay unavailable, not zero. Above-target percentages remain uncapped in text; progress-bar fill is bounded to its track.

A prior-week comparison is displayed only when the same elapsed window has nonzero matching reported duration for each line and neither week's calculation excluded readings. This is recorded-coverage comparison, not proof that every hour of the factory was captured.

The measured gap reuses existing fixed-standard reconciliation. It is not a financial loss or proof of recoverability. Missing reference pack configurations are disclosed in data notes; no pack weight is guessed. Recovery, delay and confirmed unrecovered quantities remain unclassified because current records do not establish those categories.

Downtime is clipped to the selected period and scheduled line coverage. Not Scheduled time is separate and removed. Planned overlaps take precedence; overlapping unplanned events are allocated once, oldest first. Driver ranking uses those allocated stop minutes. Existing output estimates group by machine, so per-cause tonnes are withheld rather than assigning machine totals to individual faults. Priorities recommend investigation and do not assert a root cause. Fault-driver links open the first contributing recorded fault using the existing Engineering route, so older events are not hidden by its default date filter. Planned events remain visible in the line-stop detail.

Line status and last completed-hour achievement reuse Live Operations' recorded HMI state and hourly reconciliation. Running is labelled "Running at last report", not live machine telemetry. Handover retains the recorded HMI label. Missing reports do not become 0%; an entirely Not Scheduled hour stays Not scheduled. Remaining pallets use the reconciled current run, not a guessed new job quantity.

Packaging tonnes are connected. Intake, process, finished goods and dispatch require actual stage measurements, timestamps and material/lot linkage before tonnes or dwell time can be shown. They are not inferred from packaging.

## Financial access

`GET /api/v1/dashboard/operational-intelligence` requires the existing Management session. The response advertises `production_intelligence=true`, `financial_intelligence=false`, scoped to the current single-factory deployment.

`GET /api/v1/dashboard/financial-intelligence` is also Management-protected and returns 403. Client query flags cannot enable it. No financial result provider or financial calculation exists. Placeholders are presentation-only. Future tenant entitlements must be resolved in the server policy from authenticated tenant scope before any financial provider is added; this release does not implement billing or multi-tenant provisioning.

## Validation

- Backend: **1,150 tests passed**, including all dashboard authentication checks and 12 new operational tests.
- Frontend: **565 tests passed across 45 files**, including all financial metric triggers, chart trigger, focus return, contact message, filters, manual refresh, failed refresh, missing targets, Not Scheduled and uncapped attainment.
- TypeScript/production build: passed.
- ESLint: passed without warnings.
- Local PostgreSQL integration: passed. A real HMI write of 3 pallets reconciled to 3 tonnes, 3,000 packs, 7 pallets remaining and 50% of an audited 6-tonne target. Disposable database removed afterwards.
- Browser verification: four requested viewports; no horizontal overflow or JavaScript errors. All 20 financial metric buttons opened the native modal, Escape closed it and restored focus. Screenshots inspected against the reference.
- Existing test-library deprecation/act warnings and Vite's bundle-size advisory remain; no new dependency was added to suppress them.

## Readiness

Ready for local visual review. Production deployment remains subject to approval. No new migration is required; the deployment still needs the previously introduced LineTech and weekly-target schema already used by Live Operations.

Financial values remain deliberately unavailable. Per-cause tonnes, recovery classification and upstream/downstream measurements need additional evidence before they can be reported. No commercial saving or recovered production is claimed.
