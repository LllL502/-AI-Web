export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly fields: Record<string, unknown> = {},
    public readonly requestId = '',
  ) {
    super(message)
  }
}

/**
 * 把后端的字段校验结果整理成普通用户可读的一句话。
 * DRF 可能返回字符串、数组或嵌套对象，因此需要递归提取。
 */
function firstFieldMessage(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    for (const entry of value) {
      const message = firstFieldMessage(entry)
      if (message) return message
    }
  }
  if (value && typeof value === 'object') {
    for (const entry of Object.values(value as Record<string, unknown>)) {
      const message = firstFieldMessage(entry)
      if (message) return message
    }
  }
  return ''
}

export function readableApiError(reason: unknown, fallback = '请求失败，请稍后重试。'): string {
  if (!(reason instanceof ApiError)) return fallback
  return firstFieldMessage(reason.fields) || reason.message || fallback
}

type CachedResponse = { expiresAt: number; value: unknown }

// 公开页面会在首页、广场和地图之间反复读取同一批数据。短时内存缓存既避免
// 重复请求，也会合并仍在进行中的相同请求；校区是缓存键的一部分，杜绝串校区。
const responseCache = new Map<string, CachedResponse>()
const pendingRequests = new Map<string, Promise<unknown>>()
let cacheRevision=0

function requestCacheKey(path: string): string {
  return `${localStorage.getItem('campustrace-campus') ?? 'default'}:${path}`
}

export function clearApiCache(): void {
  cacheRevision++
  responseCache.clear()
  pendingRequests.clear()
}

function readCookie(name: string): string {
  return document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=') ?? ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  const campus = localStorage.getItem('campustrace-campus')
  if (campus) headers.set('X-Campus-ID', campus)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-CSRFToken', decodeURIComponent(readCookie('csrftoken')))
  }
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin' })
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') {
      throw new ApiError('请求已取消。', 'request_aborted', 0)
    }
    // fetch 在断网、公网隧道断开或后端未启动时只会抛出没有语义的 TypeError。
    throw new ApiError(
      '无法连接服务器，请确认公网测试窗口与数据库正在运行，然后重试。',
      'network_error',
      0,
    )
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: {} }))
    const error = payload.error ?? {}
    throw new ApiError(error.message ?? '请求失败', error.code ?? 'request_failed', response.status, error.fields, error.request_id)
  }
  // 登录、发布、审核等写操作可能改变随后页面的读取结果，成功后立即失效缓存。
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) clearApiCache()
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function apiCached<T>(path: string, ttlMs = 30_000): Promise<T> {
  const key = requestCacheKey(path)
  const cached = responseCache.get(key)
  if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.value as T)
  if (cached) responseCache.delete(key)

  const pending = pendingRequests.get(key)
  if (pending) return pending as Promise<T>

  const revision=cacheRevision
  const request = api<T>(path)
    .then((value) => {
      if(revision===cacheRevision)responseCache.set(key, { expiresAt: Date.now() + ttlMs, value })
      return value
    })
    .finally(() => {if(pendingRequests.get(key)===request)pendingRequests.delete(key)})
  pendingRequests.set(key, request)
  return request
}

export async function initializeCsrf(): Promise<void> {
  await api('/auth/csrf/')
}
