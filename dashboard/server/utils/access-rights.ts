/**
 * Database-backed ROLE_MAP with in-memory cache.
 *
 * Fetches from oncoteam backend (which reads oncofiles agent_state).
 * Falls back to NUXT_ROLE_MAP env var if backend is unreachable.
 * Cache refreshes every 60s. First call triggers eager load.
 */

type RoleMap = Record<string, {
  phone?: string
  name?: string
  roles?: string[]
  patient_id?: string
  patient_ids?: string[]
}>

let _cache: RoleMap = {}
let _cacheTs = 0
let _loading: Promise<RoleMap> | null = null
const CACHE_TTL_MS = 60_000

function _parseEnvFallback(): RoleMap {
  try {
    const raw = process.env.NUXT_ROLE_MAP || '{}'
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  }
  catch {
    return {}
  }
}

async function _fetchFromBackend(): Promise<RoleMap | null> {
  const apiUrl = process.env.NUXT_ONCOTEAM_API_URL || process.env.NUXT_PUBLIC_ONCOTEAM_API_URL || ''
  const apiKey = process.env.NUXT_ONCOTEAM_API_KEY || process.env.NUXT_PUBLIC_ONCOTEAM_API_KEY || ''
  if (!apiUrl) return null

  try {
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const result = await $fetch<{ role_map: RoleMap }>(
      `${apiUrl}/api/internal/access-rights`,
      { headers, timeout: 5000 },
    )
    return result.role_map || null
  }
  catch (err) {
    console.warn('[access-rights] Backend fetch failed, using cache/env fallback:', err)
    return null
  }
}

/**
 * Get the current role map. Returns cached data if fresh,
 * otherwise fetches from backend. Never blocks longer than 5s.
 */
export async function getRoleMap(): Promise<RoleMap> {
  const now = Date.now()
  if (_cache && Object.keys(_cache).length > 0 && (now - _cacheTs) < CACHE_TTL_MS) {
    return _cache
  }

  // Coalesce concurrent fetches
  if (!_loading) {
    _loading = (async () => {
      try {
        const fromDb = await _fetchFromBackend()
        if (fromDb && Object.keys(fromDb).length > 0) {
          _cache = fromDb
          _cacheTs = Date.now()
          return _cache
        }
      }
      catch { /* fall through */ }

      // Fallback: use env var if cache is empty
      if (!_cache || Object.keys(_cache).length === 0) {
        _cache = _parseEnvFallback()
        _cacheTs = Date.now()
      }
      return _cache
    })().finally(() => { _loading = null })
  }

  return _loading
}

/**
 * Get role map synchronously from cache. Returns env var fallback
 * if cache hasn't been populated yet. Use this in sync contexts
 * (like middleware) where await isn't ideal.
 */
export function getRoleMapSync(): RoleMap {
  if (_cache && Object.keys(_cache).length > 0) return _cache
  _cache = _parseEnvFallback()
  _cacheTs = Date.now()
  return _cache
}

/**
 * Force cache invalidation (e.g., after admin update).
 */
export function invalidateRoleMapCache(): void {
  _cacheTs = 0
}

// For testing
export function _resetForTest(): void {
  _cache = {}
  _cacheTs = 0
  _loading = null
}
