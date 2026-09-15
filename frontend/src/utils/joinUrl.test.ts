import { describe, expect, it } from 'vitest'
import { joinUrl } from './joinUrl'

describe('joinUrl', () => {
  it('joins a base without a trailing slash and a path with a leading slash', () => {
    expect(joinUrl('http://127.0.0.1:8000', '/health')).toBe('http://127.0.0.1:8000/health')
  })

  it('avoids a double slash when the base ends with one', () => {
    expect(joinUrl('http://127.0.0.1:8000/', '/health')).toBe('http://127.0.0.1:8000/health')
  })

  it('adds a leading slash to the path when the base already has none', () => {
    expect(joinUrl('http://127.0.0.1:8000', 'health')).toBe('http://127.0.0.1:8000/health')
  })

  it('returns a relative path when the base is empty', () => {
    expect(joinUrl('', 'health')).toBe('/health')
  })
})
