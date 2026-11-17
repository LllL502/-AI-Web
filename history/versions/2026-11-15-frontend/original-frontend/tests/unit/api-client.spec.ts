import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiCached, clearApiCache, ApiError, readableApiError } from '../../src/api/client'

afterEach(() => {
  clearApiCache()
  localStorage.clear()
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

  it('coalesces duplicate public reads and separates campus caches', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data: { ok: true } }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([apiCached('/items/?kind=FOUND'), apiCached('/items/?kind=FOUND')])
    await apiCached('/items/?kind=FOUND')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    localStorage.setItem('campustrace-campus', '42')
    await apiCached('/items/?kind=FOUND')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('preserves the unified backend error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'forbidden', message: '没有权限', fields: { item: ['不可见'] }, request_id: 'req-1' },
    }), { status: 403, headers: { 'Content-Type': 'application/json' } })))

    await expect(api('/private/')).rejects.toMatchObject<ApiError>({
      name: 'Error', code: 'forbidden', message: '没有权限', status: 403, requestId: 'req-1',
    })
  })

  it('turns a fetch failure into an actionable server connection error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(api('/items/metadata/')).rejects.toMatchObject<ApiError>({
      code: 'network_error',
      status: 0,
      message: '无法连接服务器，请确认公网测试窗口与数据库正在运行，然后重试。',
    })
  })

  it('keeps a user cancellation distinct from a network outage', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))

    await expect(api('/assistant/prepare/', { method: 'POST' })).rejects.toMatchObject<ApiError>({
      code: 'request_aborted',
      status: 0,
      message: '请求已取消。',
    })
  })

  it('prefers a concrete field validation message over a generic envelope message', () => {
    const reason = new ApiError('请求未能完成', 'invalid', 400, {
      non_field_errors: ['地点不属于当前校区'],
    })

    expect(readableApiError(reason)).toBe('地点不属于当前校区')
  })
})
