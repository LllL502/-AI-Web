import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../../src/api/client'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
})

describe('API client contract', () => {
  it('adds the decoded CSRF token to mutation requests', async () => {
    document.cookie = 'csrftoken=token%3A2026; path=/'
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { ok: true } }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api('/items/', { method: 'POST', body: JSON.stringify({ title: '测试' }) })

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/items/')
    expect(new Headers(options.headers).get('X-CSRFToken')).toBe('token:2026')
    expect(options.credentials).toBe('same-origin')
  })

  it('preserves the unified backend error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'forbidden', message: '没有权限', fields: { item: ['不可见'] }, request_id: 'req-1' },
    }), { status: 403, headers: { 'Content-Type': 'application/json' } })))

    await expect(api('/private/')).rejects.toMatchObject<ApiError>({
      name: 'Error', code: 'forbidden', message: '没有权限', status: 403, requestId: 'req-1',
    })
  })
})
