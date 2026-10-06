# Railway deployment

## Backend

1. Push the reviewed commit to the confirmed GitHub repository. In Railway choose New Project > Deploy from GitHub repo and select that repository and branch. Use repository root as the service root; railway.json configures the backend.
2. Build: `pip install -r requirements.txt`.
3. Start: `uvicorn src.api:app --host 0.0.0.0 --port $PORT --workers 1`.
4. Set server variables through Railway: DATABASE_URL, MANAGEMENT_PIN, ENGINEERING_PIN, HMI_DEVICE_PIN, HMI_ORIGIN and DASHBOARD_ORIGIN. Use three distinct strong secrets of at least 12 characters; never use the local demo PINs. This direct Uvicorn command does not run src.serve's environment preflight. Keep one worker and one replica; sessions are process-local. Restarting requires signing in again.
5. Follow deployment_release_gate.md: verify backup/restore and migration history, then apply only unapplied reviewed migrations to the confirmed database. Migrations are deliberately not automatic on deploy. Missing migrations keep /health/ready unhealthy.
6. Generate a public domain in Railway Networking. Check /health and /health/ready over HTTPS. Verify unauthenticated writes are rejected. Do not enter factory production until standards/configuration and physical-device acceptance are complete.

## Frontend (separate deployment required)

The backend service does not serve the React app. Build the frontend from the same commit using Node 22.12+ and `npm ci` then `npm run build` in frontend. Set VITE_API_BASE_URL to the public HTTPS Railway API URL before building. Publish frontend/dist on a static host with SPA fallback to index.html. The complete repository must be available during the build because the UI imports src/production_catalogue.json.

Set HMI_ORIGIN and DASHBOARD_ORIGIN to the exact frontend HTTPS origin (no path or trailing slash). This separate-origin arrangement differs from the same-origin proxy option in the general release guide. Do not put DATABASE_URL or PINs in VITE variables. Verify API connectivity, login, hourly save, image download and native sharing on a real phone.

GitHub pushes to a connected branch can trigger Railway deployments. Confirm the linked project/environment before later pushes. Keep the previous release artefact; do not roll back schema by deleting production evidence.

Official workflow: https://docs.railway.com/guides/fastapi
Start-command guidance: https://docs.railway.com/deployments/start-command
