# Operator HMI — What's Live vs. Fixture-Backed

Stage 4 status. Read this before touching `src/features/hmi/`.

## Live (real backend calls, confirmed contracts)

- `GET /health` — API status indicator (`src/components/ApiStatus.tsx`).
- `GET /api/v1/hmi/config` — Home screen's line list, and the Report to
  Engineer screen's machine/fault-button options.
- `POST /api/v1/runs` — Start Run submission.
- `POST /api/v1/runs/{run_id}/complete` — Complete Run.

All four are called from `src/features/hmi/api.ts` only.

## Fixture-backed, awaiting API integration

No backend endpoint exists yet for these three workflows. They are
fully built and tested behind a typed service interface
(`src/features/hmi/awaitingApiIntegration.ts`), using local, clearly
labelled fixtures (`local-fixture-*` demonstration IDs) — **nothing
here ever reaches Supabase**:

- **Hourly Update** (`submitHourlyUpdate`) — computes previous/new
  total, updated pallets remaining, expected/actual output and output
  gap locally, using the same formulas documented in
  `docs/dashboard_integration.md`.
- **Planned Downtime** (`startPlannedDowntime` / `endPlannedDowntime`)
  — tracked in this device's local state only for the duration of the
  session.
- **Report to Engineer** (`reportFaultToEngineer`) — returns a demo
  reference, never sent anywhere.

When a real endpoint exists for any of these, replace only the
function body in `awaitingApiIntegration.ts` — every call site in
`HmiScreen.tsx` already matches the shape a real API call would need.

## This-device run tracking (real, not a fixture)

There is no live "is this line active" or "get this run's details"
endpoint the public HMI can call (only the PIN-protected Management
API has one, and this stage deliberately does not use it - see
`docs/hmi_integration.md`). `src/features/hmi/activeRunStorage.ts`
persists the run this device started (from a real, API-confirmed
`POST /api/v1/runs` response) in `localStorage`, so a page refresh
restores the Active Run screen instead of losing track of it or
falsely showing a completed action. It does not know about runs
started on other tablets - the real cross-device guard remains the
`409` response from `POST /api/v1/runs`.

## What remains for the API-integration stage

- Replace the three fixture functions above with real endpoints, once
  built.
- Decide whether Home's per-line "Active"/"Available" badge should
  become a real cross-device status (would need a new public
  "is this line active" endpoint - deliberately not built this stage,
  since inventing one wasn't authorised).
- Management pages (out of scope - only the navigation button exists).

## Stage 5B — Engineering React interface (implemented)

The Engineering area (`/engineering`) is no longer a placeholder. It
is a full, live-backed React interface: `src/features/engineering/`
(`EngineeringScreen.tsx`, `LoginScreen.tsx`, `Workspace.tsx`,
`FaultDetailPanel.tsx`, `RepairUpdateForm.tsx`, `HandoverForm.tsx`,
plus supporting hooks/types/validation). Every call goes to a confirmed, real
`/api/v1/engineering/*` endpoint (`docs/engineering_integration.md`,
`src/engineering_api.py`) - nothing here is fixture-backed.

- Authentication uses protected Engineering API sessions
  (`POST /api/v1/engineering/login`, a separate PIN and session store
  from Management - see `src/engineering_auth.py`). The bearer token
  is held only in React component state (`EngineeringScreen.tsx`) -
  never written to `localStorage`, `sessionStorage`, `IndexedDB` or a
  cookie, so a browser refresh always requires signing in again.
- `GET /api/v1/engineering/faults` polls every 30 seconds, pausing
  while the browser tab is hidden and refreshing immediately when it
  becomes visible again (`useFaultPolling.ts`).
- Accept, Add Repair Update, Close Fault and Hand Over Job
  (`POST .../accept`, `POST .../updates`, `POST .../close`,
  `POST .../handover`) all require an explicit confirmation step and
  never report success until FastAPI confirms it.
- Hand Over Job is shown only to the engineer who has accepted an
  open fault. It requires a note, returns the fault to unassigned /
  `Not Started` (it never reassigns it directly), and records the
  note as a `Follow Up` repair-history entry in the same database
  transaction.
- Local dev: `vite.config.ts` proxies `/api` and `/health` to FastAPI
  on `127.0.0.1:8000`.
- No real production fault was created, accepted, updated, handed
  over or closed while building or testing this interface - all
  frontend tests use mocked network responses (`vi.mock('./api')`),
  never a live Supabase connection, and manual verification of the
  live app was limited to login and read-only fault listing.
- Management pages (`/management`, `/management/performance`) remain
  outstanding - still placeholders, out of scope for Stage 5B.
