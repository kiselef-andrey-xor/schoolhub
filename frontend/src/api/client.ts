/**
 * HTTP-клиент SchoolHub.
 *
 *  - хранит пару JWT (access в памяти, refresh в localStorage);
 *  - при 401 молча обновляет access-токен ОДИН раз (очередь конкурирующих запросов)
 *    и повторяет запрос;
 *  - нормализует ошибки API в ApiError с человекочитаемым `detail`.
 *
 * Безопасность: refresh-токен в localStorage — компромисс для SPA. В prod-контуре
 * предпочтительнее httpOnly-cookie + CSRF-токен (см. README → «Безопасность»).
 */
import type { QueryParams, TokenPair } from '@/types'

const RAW_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1'
export const API_BASE = RAW_BASE.replace(/\/$/, '')

/**
 * v1.2 (безопасность сессии):
 *  - access-токен живёт ТОЛЬКО в памяти вкладки (XSS не найдёт его в storage);
 *  - refresh-токен — в httpOnly-cookie, которую ставит сервер (SameSite=strict,
 *    путь /api/v1/auth): документ не может её прочитать;
 *  - при загрузке приложения сессия молча восстанавливается через POST /auth/refresh.
 */
// вычищаем следы старой схемы хранения refresh-токена в localStorage
try {
  localStorage.removeItem('schoolhub.access')
  localStorage.removeItem('schoolhub.refresh')
  sessionStorage.removeItem('schoolhub.access')
} catch {
  /* приватный режим и т.п. */
}

let accessToken: string | null = null

export class ApiError extends Error {
  status: number
  code?: string

  constructor(status: number, detail: string, code?: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Наблюдатели сессии: authStore подписывается, чтобы синхронизировать профиль. */
type Listener = (event: 'login' | 'logout', tokens?: TokenPair) => void
const listeners = new Set<Listener>()

export function onSessionChange(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function emit(event: 'login' | 'logout', tokens?: TokenPair) {
  listeners.forEach((fn) => fn(event, tokens))
}

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null) {
  accessToken = token
  if (token) emit('login')
}

export function clearTokens() {
  accessToken = null
  emit('logout')
}

export function isAuthenticated(): boolean {
  return Boolean(accessToken)
}

// ------------------------------------------------------------------ internals
function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      url.searchParams.set(key, String(value))
    })
  }
  return url.toString()
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = `Ошибка ${response.status}`
  let code: string | undefined
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') detail = body.detail
    else if (Array.isArray(body?.detail)) {
      // ошибки валидации pydantic
      detail = body.detail
        .map((e: { loc?: (string | number)[]; msg?: string }) => `${(e.loc ?? []).slice(1).join('.')}: ${e.msg}`)
        .join('; ')
    }
    code = body?.code
  } catch {
    /* тело не JSON — оставляем статус */
  }
  return new ApiError(response.status, detail, code)
}

let refreshPromise: Promise<string | null> | null = null

/** Молчаливое обновление access-токена по httpOnly-cookie (single-flight на вкладку). */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
        })
        if (!res.ok) {
          clearTokens()
          return null
        }
        const tokens = (await res.json()) as TokenPair
        setAccessToken(tokens.access_token)
        return tokens.access_token
      } catch {
        clearTokens()
        return null
      } finally {
        refreshPromise = null
      }
    })()
  }
  return refreshPromise
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  form?: FormData
  params?: QueryParams
  raw?: boolean
  auth?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, form, params, raw = false, auth = true } = options

  const headers: Record<string, string> = {}
  if (auth) {
    const token = getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  // для FormData заголовок ставит браузер (с boundary)

  const response = await fetch(buildUrl(path, params), {
    method,
    headers,
    credentials: 'same-origin',
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  })

  if (response.status === 401 && auth) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      headers.Authorization = `Bearer ${newToken}`
      const retry = await fetch(buildUrl(path, params), {
        method,
        headers,
        credentials: 'same-origin',
        body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      })
      if (!retry.ok) throw await parseError(retry)
      return raw ? ((await retry.blob()) as unknown as T) : ((await retry.json()) as T)
    }
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  if (raw) return (await response.blob()) as unknown as T
  return (await response.json()) as T
}

// --------------------------------------------------------------------- export
export const http = {
  get: <T>(path: string, params?: QueryParams) => request<T>(path, { params }),
  post: <T>(path: string, body?: unknown, params?: QueryParams) => request<T>(path, { method: 'POST', body, params }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', form }),
  blob: (path: string, params?: QueryParams) => request<Blob>(path, { params, raw: true }),
  public: {
    get: <T>(path: string, params?: QueryParams) => request<T>(path, { params, auth: false }),
    post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body, auth: false }),
  },
}

/** Скачивание файла с авторизацией (заголовок нельзя добавить в <a href>). */
export async function downloadAuthorized(path: string, filename: string, params?: QueryParams) {
  const blob = await http.blob(path, params)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/** Blob URL для инлайн-превью (PDF в <iframe>). Освобождать через URL.revokeObjectURL. */
export async function blobUrl(path: string, params?: QueryParams): Promise<string> {
  const blob = await http.blob(path, params)
  return URL.createObjectURL(blob)
}
