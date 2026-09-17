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
| Complete Run | Explicit warning before closing the run |
| Run Completed | Confirmation, back to Home |
| Exit or Restart | Confirms, explains the run stays Active - never force-closes |

**Live endpoints** (`src/features/hmi/api.ts`): `GET /health`,
`GET /api/v1/hmi/config`, `POST /api/v1/runs`,
`POST /api/v1/runs/{run_id}/complete`.

**Fixture-backed, awaiting API integration**
(`src/features/hmi/awaitingApiIntegration.ts`): hourly updates,
planned downtime, report-to-engineer - no backend endpoint exists yet
for these. See `HMI_FRONTEND_STATUS.md` for the full breakdown of
what's live vs. fixture-backed and what remains.

The in-progress run is persisted to this device's `localStorage`
(`activeRunStorage.ts`) so refreshing the browser restores the Active
Run screen instead of losing track of it - this reflects a real,
API-confirmed run, not a fixture.

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
