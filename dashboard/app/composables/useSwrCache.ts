/**
 * Stale-while-revalidate cache backed by sessionStorage.
 *
 * Mirrors the oncofiles dashboard.html _swrGet/_swrSet helpers
 * (oncofiles#469 Phase 5, oncoteam#424 Task 4). The purpose is to keep
 * the Recent Labs / Latest Briefing / Timeline cards populated when a
 * refetch fails — instead of tearing the UI down to empty-state
 * "Data temporarily unavailable" placeholders during a breaker trip.
 *
 * Keys are per-patient so cross-patient leak is impossible, 10-min hard
 * TTL so we never serve genuinely old data as fresh.
 */

const SWR_MAX_AGE_MS = 10 * 60 * 1000
const SWR_PREFIX = 'oncoteamCache:'

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.sessionStorage !== 'undefined'
}

function swrKey(patientId: string, path: string): string {
  return `${SWR_PREFIX}${patientId || 'default'}:${path}`
}

interface SwrEntry<T> {
  data: T
  cached_at: number
}

export interface SwrHit<T> {
  data: T
  ageMs: number
}

export function swrGet<T>(patientId: string, path: string): SwrHit<T> | null {
  if (!isBrowser()) return null
  try {
    const raw = window.sessionStorage.getItem(swrKey(patientId, path))
    if (!raw) return null
    const entry = JSON.parse(raw) as SwrEntry<T>
    if (!entry || typeof entry.cached_at !== 'number') return null
    const ageMs = Date.now() - entry.cached_at
    if (ageMs > SWR_MAX_AGE_MS) {
      window.sessionStorage.removeItem(swrKey(patientId, path))
      return null
    }
    return { data: entry.data, ageMs }
  } catch {
    return null
  }
}

export function swrSet<T>(patientId: string, path: string, data: T): void {
  if (!isBrowser()) return
  try {
    const entry: SwrEntry<T> = { data, cached_at: Date.now() }
    window.sessionStorage.setItem(swrKey(patientId, path), JSON.stringify(entry))
  } catch {
    // quota / serialization errors — non-fatal
  }
}

export function swrClearAll(): void {
  if (!isBrowser()) return
  try {
    const keys: string[] = []
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const k = window.sessionStorage.key(i)
      if (k && k.startsWith(SWR_PREFIX)) keys.push(k)
    }
    keys.forEach((k) => window.sessionStorage.removeItem(k))
  } catch {
    // ignore
  }
}

export function swrClearPatient(patientId: string): void {
  if (!isBrowser()) return
  try {
    const prefix = `${SWR_PREFIX}${patientId || 'default'}:`
    const keys: string[] = []
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const k = window.sessionStorage.key(i)
      if (k && k.startsWith(prefix)) keys.push(k)
    }
    keys.forEach((k) => window.sessionStorage.removeItem(k))
  } catch {
    // ignore
  }
}

export const SWR_CONFIG = {
  MAX_AGE_MS: SWR_MAX_AGE_MS,
  PREFIX: SWR_PREFIX,
}

/**
 * Path-prefix allowlist for SWR-backed endpoints. Opt-in: only the cards
 * the user actually looks at when oncofiles trips get cached. Expanding
 * this list is a conscious decision — we do NOT want to cache e.g.
 * agent runs or WhatsApp history across refreshes.
 */
export const SWR_PATHS = ['/labs', '/briefings', '/timeline'] as const

export function isSwrPath(path: string): boolean {
  return SWR_PATHS.some((p) => path === p || path.startsWith(`${p}?`))
}
