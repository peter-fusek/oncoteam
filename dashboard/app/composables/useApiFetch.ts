/**
 * Low-level fetch wrapper with circuit-breaker-aware retries.
 *
 * Contract mirrors oncofiles apiFetch (see oncofiles#469 + oncoteam#424):
 *  - 503 → throw `{ status: 503, retryAfterMs }` immediately. The banner IS
 *    the retry; retrying inside the upstream cooldown is guaranteed to fail.
 *  - 500/502/504 / AbortError → exponential jitter backoff (base 500ms, cap
 *    5s, ±25% jitter), up to `retryBudget` attempts.
 *  - 401 → throw 'Unauthorized' so the caller can surface re-auth UI.
 *  - other non-ok → throw `{ status, ... }` without retry.
 *
 * `Retry-After` is parsed in both RFC 7231 forms: seconds OR HTTP-date.
 */

export interface ApiFetchError extends Error {
  status?: number
  retryAfterMs?: number
}

export function parseRetryAfter(headerValue: string | null | undefined): number | null {
  if (!headerValue) return null
  const n = parseInt(headerValue, 10)
  if (!Number.isNaN(n) && n >= 0) return n * 1000
  const d = Date.parse(headerValue)
  if (!Number.isNaN(d)) return Math.max(0, d - Date.now())
  return null
}

export function jitterMs(attempt: number, baseMs = 500, maxMs = 5000): number {
  const exp = Math.min(maxMs, baseMs * Math.pow(2, attempt - 1))
  const jitter = exp * 0.25 * (Math.random() * 2 - 1)
  return Math.max(0, Math.floor(exp + jitter))
}

export interface FetchOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  retryBudget?: number
  perRequestTimeoutMs?: number
  signal?: AbortSignal
}

export async function apiFetch<T>(url: string, opts: FetchOptions = {}): Promise<T> {
  const retryBudget = opts.retryBudget ?? 3
  const perRequestTimeoutMs = opts.perRequestTimeoutMs ?? 25000

  let attempt = 0
  while (true) {
    const ac = new AbortController()
    const tid = setTimeout(() => ac.abort(), perRequestTimeoutMs)
    if (opts.signal) {
      if (opts.signal.aborted) ac.abort()
      else opts.signal.addEventListener('abort', () => ac.abort(), { once: true })
    }
    try {
      const init: RequestInit = {
        method: opts.method || 'GET',
        headers: opts.headers,
        signal: ac.signal,
      }
      if (opts.body !== undefined) {
        init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)
        init.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
      }
      const resp = await fetch(url, init)
      clearTimeout(tid)

      if (resp.status === 401) {
        const err: ApiFetchError = new Error('Unauthorized')
        err.status = 401
        throw err
      }

      // Breaker-open — surface immediately with Retry-After so the caller
      // can render the countdown banner. No inner retry inside the cooldown.
      if (resp.status === 503) {
        const retryAfterMs = parseRetryAfter(resp.headers.get('Retry-After'))
        const err: ApiFetchError = new Error('HTTP 503')
        err.status = 503
        err.retryAfterMs = retryAfterMs ?? 30000
        throw err
      }

      // Transient — retry with jitter up to budget.
      if (resp.status === 500 || resp.status === 502 || resp.status === 504) {
        if (attempt < retryBudget) {
          attempt += 1
          await new Promise((r) => setTimeout(r, jitterMs(attempt)))
          continue
        }
        const err: ApiFetchError = new Error(`HTTP ${resp.status}`)
        err.status = resp.status
        throw err
      }

      if (!resp.ok) {
        const err: ApiFetchError = new Error(`HTTP ${resp.status}`)
        err.status = resp.status
        throw err
      }
      return (await resp.json()) as T
    } catch (e) {
      clearTimeout(tid)
      const err = e as ApiFetchError
      // Per-request timeout → same retry path as transient 5xx.
      if (err && err.name === 'AbortError' && !(opts.signal?.aborted)) {
        if (attempt < retryBudget) {
          attempt += 1
          await new Promise((r) => setTimeout(r, jitterMs(attempt)))
          continue
        }
        const t: ApiFetchError = new Error('request timed out')
        t.status = 0
        throw t
      }
      throw err
    }
  }
}
