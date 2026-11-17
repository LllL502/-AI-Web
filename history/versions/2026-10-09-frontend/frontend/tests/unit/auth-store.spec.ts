import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../src/stores/auth'

const jsonResponse = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllGlobals()
  })

  it('marks bootstrap ready and retains an authenticated role', async () => {
    const user = { id: 1, username: 'staff', display_name: '协调员', email: '', role: 'STAFF' }
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: { csrf: true } }))
      .mockResolvedValueOnce(jsonResponse({ data: user })))
    const store = useAuthStore()

    await store.bootstrap()

    expect(store.ready).toBe(true)
    expect(store.user).toEqual(user)
    expect(store.isManagement).toBe(true)
  })

  it('falls back to an anonymous ready state when session lookup fails', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: { csrf: true } }))
      .mockResolvedValueOnce(jsonResponse({ error: { message: '未登录' } }, 403)))
    const store = useAuthStore()

    await store.bootstrap()

    expect(store.ready).toBe(true)
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})
