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
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: {} }))
    const error = payload.error ?? {}
    throw new ApiError(error.message ?? '请求失败', error.code ?? 'request_failed', response.status, error.fields, error.request_id)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function initializeCsrf(): Promise<void> {
  await api('/auth/csrf/')
}
