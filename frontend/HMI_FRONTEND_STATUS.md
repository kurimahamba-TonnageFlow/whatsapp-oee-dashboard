# Operator HMI — Frontend Status

Stage 6B2 status. Read this before touching `src/features/hmi/`.

Every Stage 6B1 capture endpoint the HMI now calls needs
`migrations/0003_pulse_phase1_foundation.sql`, which was **applied
successfully during Stage 6B4**. The backend and this frontend must be
released together.

## Live (real backend calls, confirmed contracts)

Every HMI workflow is backed by a real endpoint. No fixtures remain:
`src/features/hmi/awaitingApiIntegration.ts` has been deleted, and every
call goes through `src/features/hmi/api.ts`.

| Workflow | Endpoint |
| --- | --- |
| API status indicator (`src/components/ApiStatus.tsx`) | `GET /health` |
| Home line list, Report to Engineer machine/button options | `GET /api/v1/hmi/config` |
| Home cross-device line availability | `GET /api/v1/hmi/lines` |
| Start Run | `POST /api/v1/runs` |
| Active-run recovery | `GET /api/v1/runs/{run_id}/hmi-state` |
| Hourly Update | `POST /api/v1/runs/{run_id}/hourly-updates` |
| Planned Downtime start / end | `POST /api/v1/runs/{run_id}/planned-downtime`, `POST /api/v1/planned-downtime/{id}/end` |
| Report to Engineer | `POST /api/v1/runs/{run_id}/faults` |
| Start / Complete Changeover | `POST /api/v1/runs/{run_id}/changeovers`, `POST /api/v1/changeovers/{id}/complete` |
| Complete Run review | `POST /api/v1/runs/{run_id}/completion-preview` |
| Complete Run | `POST /api/v1/runs/{run_id}/complete` |

No figure shown on the tablet is calculated in the browser. Every total,
percentage, expected-output and waste figure comes from the backend
response (`src/pulse_calculations.py`); the HMI formats and displays it.

## Idempotent writes

Every write sends an `Idempotency-Key` header
(`src/features/hmi/idempotency.ts`). The key is generated when the
operator commits an action and reused for every retry of that same
action, so a double tap, a lost response or a refresh mid-request cannot
produce a second hourly update, fault, changeover or run completion. The
guarantee is enforced server-side by the `hmi_idempotency_keys` table, in
one transaction with the business rows — not by a client-side timer, and
not by the previous five-minute duplicate guard, which has been removed.

Keys are retained for 90 days, with `created_at` and `expires_at` set by
database defaults rather than by the client. An expired key may be reused
as a new action; a live key never can. Removing expired rows is a
separate maintenance call (`delete_expired_idempotency_keys`), never part
of a write — see `docs/hmi_integration.md`.

## Cross-device line state

Home no longer decides availability from this device's storage. It polls
`GET /api/v1/hmi/lines` every 20 seconds
(`src/features/hmi/useLineStatePolling.ts`), pausing while the tab is
hidden, refreshing immediately when it becomes visible again, and keeping
at most one request in flight.

- A line running on **any** tablet shows **Run Active** with the
  technician, shift, customer and product, plus whether planned
  downtime, a changeover or an engineering fault is open, and whether the
  run has gone quiet (75-minute threshold).
- An active line offers **Open Active Run**, never Start Run. Opening it
  reads the full state from `GET /api/v1/runs/{run_id}/hmi-state` and
  only then adopts the run on this device.
- If line status cannot be loaded, Home says so and **disables Start
  Run**. An empty `localStorage` is never taken as proof that a line is
  free.
- The database uniqueness constraint stays the final authority. If two
  tablets still race, the loser's `409` from `POST /api/v1/runs`
  re-reads the line state and explains that another device started the
  run first; nothing is retried automatically and no second run is
  created.

## This-device run tracking

`src/features/hmi/activeRunStorage.ts` stores only `{runId,
productionLine}` in `localStorage`. Everything else — totals, pallets
remaining, open planned downtime, open changeover — is re-read from
`GET /api/v1/runs/{run_id}/hmi-state` on load, so nothing shown on the
tablet is local-only state. If the stored run no longer exists the entry
is cleared and the operator returns to Home.

## What remains

- Management dashboard pages (`/management`, `/management/performance`)
  remain placeholders — not built. The backend reporting endpoints exist
  (`src/dashboard_api.py`, `src/dashboard_reports.py`); no dashboard
  frontend has been built.

## Engineering React interface (implemented)

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
- Close Fault requires the maintenance-preventability answer (Yes / No
  / Unsure). Nothing is preselected, the close is blocked until the
  engineer chooses, and a failed close keeps both the answer and the
  typed repair detail on screen. Interim repair updates do not ask it.
  This needs migration 0003, which was applied successfully during
  Stage 6B4, like the rest of Stage 6B.
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
  outstanding - still placeholders.
