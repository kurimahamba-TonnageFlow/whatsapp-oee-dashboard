/**
 * Safely joins an API base URL and a request path, avoiding a missing
 * or duplicated slash between them. When base is empty (e.g.
 * VITE_API_BASE_URL is unset), returns a same-origin relative path
 * instead of throwing - the request will simply fail safely later.
 */
export function joinUrl(base: string, path: string): string {
  const normalisedPath = path.startsWith('/') ? path : `/${path}`

  if (!base) {
    return normalisedPath
  }

  const trimmedBase = base.endsWith('/') ? base.slice(0, -1) : base

  return `${trimmedBase}${normalisedPath}`
}
