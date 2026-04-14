import { getActivePatient } from './whatsapp-session'

/**
 * Runtime set of admin-approved WhatsApp phone numbers.
 * Phones added here bypass the allowlist after completing onboarding.
 * In-memory cache — backend (oncofiles) is the source of truth.
 * If a phone is not in the local cache, we double-check with the backend
 * before routing to onboarding.
 */
const approvedPhones = new Set<string>()
const phoneToPatient = new Map<string, string>()

export function addApprovedPhone(phone: string): void {
  approvedPhones.add(phone)
}

export function isApproved(phone: string): boolean {
  return approvedPhones.has(phone)
}

/**
 * Check backend for approved status when local cache misses.
 * Returns 'approved' if confirmed, 'denied' if explicitly not approved,
 * or 'error' if backend is unreachable (caller must fail closed).
 */
export async function checkApprovedWithBackend(
  phone: string,
  oncoteamApiUrl: string,
  apiKey: string,
): Promise<'approved' | 'denied' | 'error'> {
  if (approvedPhones.has(phone)) return 'approved'
  try {
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const result = await $fetch<{ phone: string; status: string; approved: boolean }>(
      `${oncoteamApiUrl}/api/internal/onboarding-status`,
      {
        method: 'POST',
        body: { phone },
        headers,
        timeout: 3000,
      },
    )
    if (result.approved) {
      approvedPhones.add(phone)
      return 'approved'
    }
    return 'denied'
  }
  catch {
    console.error(`[approved-phones] Backend unreachable for phone check — failing closed`)
    return 'error'
  }
}

export function getApprovedPhones(): string[] {
  return [...approvedPhones]
}

export function setPhonePatient(phone: string, patientId: string): void {
  phoneToPatient.set(phone, patientId)
}

export function resolvePatientIdFromPhone(phone: string): string {
  return phoneToPatient.get(phone) || ''
}

/**
 * Get the currently active patient for a phone.
 * Priority: session override (via "prepni"/"switch") → role-map default → 'q1b'.
 */
export function getActivePatientForPhone(phone: string): string {
  const sessionPatient = getActivePatient(phone)
  if (sessionPatient) return sessionPatient
  return resolvePatientIdFromPhone(phone) || 'q1b'
}

/**
 * Get user identity (name, roles) for a phone from ROLE_MAP.
 * Returns first matching entry's name and roles.
 */
export function getUserInfoForPhone(phone: string, roleMapRaw: string | Record<string, { phone?: string; name?: string; roles?: string[] }>): { name: string; roles: string[] } {
  try {
    const roleMap = typeof roleMapRaw === 'string' ? JSON.parse(roleMapRaw || '{}') : roleMapRaw || {}
    const normalized = phone.replace(/[\s\-()]/g, '')
    for (const config of Object.values(roleMap) as Array<{ phone?: string; name?: string; roles?: string[] }>) {
      const configPhone = config.phone?.replace(/[\s\-()]/g, '') || ''
      if (configPhone === normalized) {
        return { name: config.name || '', roles: config.roles || [] }
      }
    }
  }
  catch { /* ignore parse errors */ }
  return { name: '', roles: [] }
}

/**
 * Get all allowed patient IDs for a phone from ROLE_MAP.
 * Merges patient_ids from all ROLE_MAP entries sharing this phone.
 */
export function getAllowedPatientIdsForPhone(phone: string, roleMapRaw: string | Record<string, { phone?: string; patient_ids?: string[]; patient_id?: string }>): string[] {
  try {
    const roleMap = typeof roleMapRaw === 'string' ? JSON.parse(roleMapRaw || '{}') : roleMapRaw || {}
    const normalized = phone.replace(/[\s\-()]/g, '')
    const ids = new Set<string>()
    for (const config of Object.values(roleMap) as Array<{ phone?: string; patient_ids?: string[]; patient_id?: string }>) {
      const configPhone = config.phone?.replace(/[\s\-()]/g, '') || ''
      if (configPhone === normalized) {
        if (config.patient_ids) config.patient_ids.forEach(id => ids.add(id))
        else if (config.patient_id) ids.add(config.patient_id)
      }
    }
    return [...ids]
  }
  catch { return [] }
}
