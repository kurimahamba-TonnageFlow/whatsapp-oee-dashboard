import { describe, expect, it } from 'vitest'
import viteConfig from './vite.config'

type ProxyTarget = string | { target?: string }

/**
 * Regression test for the Engineering login "request could not be
 * completed" fault: with no dev proxy, relative API calls (the safe
 * fallback when VITE_API_BASE_URL is unset - see src/utils/joinUrl.ts)
 * resolve against the Vite dev server instead of FastAPI, so POSTs
 * never reach Uvicorn. This asserts the proxy stays wired to the
 * backend so that regression can't come back silently.
 */
describe('vite dev server proxy', () => {
  const proxy = (viteConfig as { server?: { proxy?: Record<string, ProxyTarget> } }).server?.proxy

  it('forwards /api requests to the FastAPI backend', () => {
    expect(proxy?.['/api']).toBe('http://127.0.0.1:8000')
  })

  it('forwards /health requests to the FastAPI backend', () => {
    expect(proxy?.['/health']).toBe('http://127.0.0.1:8000')
  })
})
