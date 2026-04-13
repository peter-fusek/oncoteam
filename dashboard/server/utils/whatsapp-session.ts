/**
 * Per-phone active patient session state for WhatsApp multi-patient switching.
 *
 * Separate from the role-map phoneToPatient Map in approved-phones.ts.
 * The role-map default is read-only; this module holds the user's runtime choice
 * (via "prepni"/"switch" command). Resets on deploy — acceptable for in-memory state.
 */

const SESSION_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours

interface PatientSession {
  patientId: string
  setAt: number
}

const sessions = new Map<string, PatientSession>()

function pruneExpired(): void {
  const now = Date.now()
  for (const [phone, s] of sessions) {
    if (now - s.setAt > SESSION_TTL_MS) sessions.delete(phone)
  }
}

/** Get the user's session-chosen active patient, if set and not expired. */
export function getActivePatient(phone: string): string | undefined {
  pruneExpired()
  return sessions.get(phone)?.patientId
}

/** Set the active patient for a phone (via "prepni"/"switch" command). */
export function setActivePatient(phone: string, patientId: string): void {
  pruneExpired()
  sessions.set(phone, { patientId, setAt: Date.now() })
}

/** Clear the active patient session for a phone. */
export function clearActivePatient(phone: string): void {
  sessions.delete(phone)
}
