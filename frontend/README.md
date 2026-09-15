# TonnageFlow Pulse — Frontend

This is the foundation for the Pulse React frontend: routing shell,
design tokens, and a typed API client that talks to the existing
FastAPI backend (`src/api.py` at the repository root). It does **not**
yet contain the real HMI, Dashboard, Management, or Engineering
screens - each route currently renders a placeholder confirming that
routing and the API connection work.

## Contents

```
frontend/
  public/            static assets served as-is
  src/
    api/             central typed fetch client (client.ts)
    components/      shared UI components (ApiStatus)
    features/        per-area screens (hmi, engineering, management, dashboard)
    hooks/           shared React hooks (useApiStatus)
    layouts/         AppShell (header, nav, content area)
    pages/           route-level pages composing a layout + feature
    routes/          React Router route definitions
    styles/          design tokens + global CSS
    types/           shared TypeScript types for confirmed backend contracts
    utils/           small pure helpers (joinUrl)
```

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
