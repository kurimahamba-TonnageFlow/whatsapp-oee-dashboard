# TonnageFlow Pulse — Frontend

The Pulse React frontend: routing shell, design tokens, a typed API
client that talks to the existing FastAPI backend (`src/api.py` at the
repository root), and the real operator HMI at `/hmi`. Dashboard,
Management, and Engineering still render placeholders - only their
navigation buttons exist so far.

## Contents

```
frontend/
  public/            static assets served as-is
  src/
    api/             central typed fetch client (client.ts)
    components/      shared UI components (ApiStatus)
    features/
      hmi/           the real operator HMI (see below)
      engineering/    placeholder
      management/     placeholder
      dashboard/      placeholder
    hooks/           shared React hooks (useApiStatus)
    layouts/         AppShell (header, nav, content area)
    pages/           route-level pages composing a layout + feature
    routes/          React Router route definitions
    styles/          design tokens + global CSS
    types/           shared TypeScript types for confirmed backend contracts
    utils/           small pure helpers (joinUrl)
```

## Operator HMI (`/hmi`)

Habit loop: **SEE → ACT → CONFIRM → PROGRESS → COMPLETE**. Tablet
landscape first; also works at ~375px (mobile), ~768-1180px (tablet)
and ~1440px (desktop). Dark theme scoped to `.hmi-screen`
(`src/features/hmi/hmi.css`) - a considered design, not a verified
match to a real reference (none was ever supplied to this project).

Screens (`src/features/hmi/screens/`), driven by one state machine in
`HmiScreen.tsx`:

| Screen | Purpose |
| --- | --- |
| Home | Brand, UK date/time, current shift, line selection (from `GET /api/v1/hmi/config`), Engineering/Management access |
| Start Run form | All required fields, validated beside each field |
| Review Run | Shows everything entered before submitting |
| Run Started | `✓ RUN STARTED` for ~1.5s, then Active Run |
| Active Run | Live progress, output figures, downtime totals, primary actions |
| Hourly Update | Previous/new total, updated remaining, expected/actual/gap |
| Planned Downtime | Start/show elapsed/confirm-end |
| Report to Engineer | Machine + fault reason (from config where available) + note |
| Start Changeover | Next product/customer/format for the line; opens a paired planned stop |
| Complete Changeover | Closes the changeover once the new run's first acceptable packs are produced |
| Complete Run | Explicit warning before closing the run |
| Run Completed | Confirmation, back to Home |
| Exit or Restart | Confirms, explains the run stays Active - never force-closes |

**Live endpoints** - every HMI workflow calls the real FastAPI backend
through `src/features/hmi/api.ts`; no fixtures remain:

| Workflow | Endpoint |
| --- | --- |
| API status indicator | `GET /health` |
| Line list, machine/button options | `GET /api/v1/hmi/config` |
| Cross-device line availability (polled every 20s) | `GET /api/v1/hmi/lines` |
| Start Run | `POST /api/v1/runs` |
| Active-run recovery | `GET /api/v1/runs/{run_id}/hmi-state` |
| Hourly Update | `POST /api/v1/runs/{run_id}/hourly-updates` |
| Planned Downtime start / end | `POST /api/v1/runs/{run_id}/planned-downtime`, `POST /api/v1/planned-downtime/{id}/end` |
| Report to Engineer | `POST /api/v1/runs/{run_id}/faults` |
| Start / Complete Changeover | `POST /api/v1/runs/{run_id}/changeovers`, `POST /api/v1/changeovers/{id}/complete` |
| Complete Run review / Complete Run | `POST /api/v1/runs/{run_id}/completion-preview`, `POST /api/v1/runs/{run_id}/complete` |

Every write sends an `Idempotency-Key` header
(`src/features/hmi/idempotency.ts`), reused for every retry of the same
action, so a double tap or a retry after a timeout can never write
twice. All figures shown are calculated by the backend. These endpoints
need `migrations/0003_pulse_phase1_foundation.sql`, which was applied
during Stage 6B4. See `HMI_FRONTEND_STATUS.md` for the full breakdown
and `docs/hmi_integration.md` for the request/response contracts.

This device's `localStorage` (`activeRunStorage.ts`) remembers only
which run the tablet is working on. After a refresh the HMI re-reads
that run's current state from `GET /api/v1/runs/{run_id}/hmi-state`;
production totals, planned downtime and changeovers always come from
the database, never from the device.

## Requirements

Node 20 or later (developed and tested with Node 24).

## Install

```
cd frontend
npm install
```

## Configure

```
cp .env.example .env
```

Edit `.env` and set `VITE_API_BASE_URL` to wherever the backend
(`uvicorn src.api:app`) is running - `http://127.0.0.1:8000` for local
development. `.env` is git-ignored; only `.env.example` is committed.

## Run in development mode

```
npm run dev
```

Vite prints the local preview URL (typically `http://localhost:5173`).

## Run tests

```
npm test
```

Uses Vitest + React Testing Library + jsdom.

## Lint

```
npm run lint
```

## Build for production

```
npm run build
```

Type-checks with `tsc -b` then builds with Vite into `frontend/dist/`.
