import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
// Local dev only: forwards same-origin /api and /health requests to the
// FastAPI backend. Without this, calls made via a relative path (the
// safe fallback in src/utils/joinUrl.ts when VITE_API_BASE_URL is unset)
// resolve against the Vite dev server itself instead of FastAPI - GETs
// can look "connected" via Vite's HTML fallback while POSTs 404 before
// ever reaching Uvicorn.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
