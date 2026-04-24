/**
 * Database-backed ROLE_MAP with in-memory cache.
 *
 * Fetches from oncoteam backend (which reads oncofiles agent_state).
 * Falls back to NUXT_ROLE_MAP env var if backend is unreachable.
 * Cache refreshes every 60s. First call triggers eager load.
 */

export type UserConfig = {
  phone?: string
  name?: string
  // Legacy shape (pre-#422 Part B): flat roles applied to every patient_id.
  roles?: string[]
  patient_id?: string
  patient_ids?: string[]
  // New shape (#422 Part B): per-patient role mapping. When present, wins
  // over `roles[0]`. Keys are patient IDs; values are role strings from
  // KNOWN_ROLES. Missing patient → user has no visibility into that patient.
  patient_roles?: Record<string, string>
}
type RoleMap = Record<string, UserConfig>

// Role vocabulary. `admin-readonly` + `family-readonly` are the
// read-only-group roles rendered under the 🔒 separator in the dropdown.
// Everything else grants write access + full clinical UI.
export const WRITABLE_ROLES = new Set(['advocate', 'patient', 'doctor'])
export const READONLY_ROLES = new Set(['admin-readonly', 'family-readonly'])
export const KNOWN_ROLES = new Set([...WRITABLE_ROLES, ...READONLY_ROLES])

/**
 * Resolve a user's role for a specific patient.
 *
 * Precedence: `patient_roles[patientId]` (new shape) > `roles[0]` (legacy
 * flat) > 'advocate' (safe default — writable so the UI still surfaces a
 * clear permission denied from the backend instead of silently hiding).
 *
 * Returns `null` when the user has no role for that patient — callers
 * should treat null as "no visibility" and filter the patient out of
 * listings.
 */
export function getRoleForPatient(uc: UserConfig | undefined, patientId: string): string | null {
  if (!uc) return null
  if (uc.patient_roles && patientId in uc.patient_roles) {
    return uc.patient_roles[patientId] || null
  }
  // Legacy fallback: flat roles apply to any patient_id listed.
  const flatIds = uc.patient_ids || (uc.patient_id ? [uc.patient_id] : [])
  if (flatIds.includes(patientId) && uc.roles?.length) {
    return uc.roles[0]
  }
  return null
}

export function isReadOnlyRole(role: string | null | undefined): boolean {
  return !!role && READONLY_ROLES.has(role)
}

/**
 * Union of patient IDs this user can see across both shapes. Used by
 * session-patch to build `patientIds` without losing any access.
 */
export function visiblePatientIds(uc: UserConfig | undefined): string[] {
  if (!uc) return []
  const out = new Set<string>()
  if (uc.patient_roles) {
    for (const pid of Object.keys(uc.patient_roles)) out.add(pid)
  }
  if (uc.patient_ids) {
    for (const pid of uc.patient_ids) out.add(pid)
  }
  if (uc.patient_id) out.add(uc.patient_id)
  return [...out]
}

/**
 * Build a per-patient role dict from a UserConfig. Populates every
 * visible patient; uses legacy `roles[0]` as the default when the new
 * shape is missing an entry. Callers store this on `session.user` so
 * the dashboard dropdown can render per-patient badges.
 */
export function buildPatientRoles(uc: UserConfig | undefined): Record<string, string> {
  if (!uc) return {}
  const out: Record<string, string> = {}
  for (const pid of visiblePatientIds(uc)) {
    const r = getRoleForPatient(uc, pid)
    if (r) out[pid] = r
  }
  return out
}

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
