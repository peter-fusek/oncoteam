/**
 * Server middleware to patch stale sessions from pre-Sprint 17.
 * Sessions created before role support lack `roles`, `activeRole`, and `phone`.
 * This patches them on-the-fly using the roleMap so users don't need to re-login.
 */
import { buildPatientRoles, getRoleMapSync, visiblePatientIds } from '../utils/access-rights'

export default defineEventHandler(async (event) => {
  // Only patch page requests, not API calls or static assets
  const path = getRequestURL(event).pathname
  if (path.startsWith('/api/') || path.startsWith('/_nuxt/') || path.startsWith('/__nuxt')) return

  const session = await getUserSession(event)
  if (!session.user?.email) return
  // Skip if session is fully patched AND patientIds matches roleMap AND
  // patientRoles are present on the session (new field added in #422 Part B).
  const existingIds = session.user.patientIds as string[] | undefined
  const existingRoles = session.user.patientRoles as Record<string, string> | undefined
  const hasDuplicates = existingIds && existingIds.length !== new Set(existingIds).size
  // Re-patch when roleMap visible-patient-ids OR patient_roles changed.
  let roleMapChanged = false
  try {
    const rm = getRoleMapSync()
    const email = session.user.email as string
    const uc = rm[email]
    if (uc) {
      const expected = [...new Set(visiblePatientIds(uc))]
      const expectedRoles = buildPatientRoles(uc)
      const idsDiffer = !existingIds
        || existingIds.length !== expected.length
        || !expected.every((id: string) => existingIds.includes(id))
      const rolesDiffer = !existingRoles
        || Object.keys(expectedRoles).length !== Object.keys(existingRoles).length
        || Object.entries(expectedRoles).some(([pid, r]) => existingRoles[pid] !== r)
      roleMapChanged = idsDiffer || rolesDiffer
    }
  } catch { /* re-patch on parse error */ }
  if (
    !roleMapChanged
    && session.user.roles && Array.isArray(session.user.roles)
    && session.user.patientId
    && existingIds && !hasDuplicates
    && existingRoles
  ) return

  const roleMap = getRoleMapSync()

  const email = session.user.email as string
  const userConfig = roleMap[email] || { roles: ['advocate'] }
  const roles = userConfig.roles || ['advocate']

  // Visible patient set — union of both legacy and new shape so users
  // don't silently lose access during migration.
  const visibleIds = visiblePatientIds(userConfig)
  const patientId = userConfig.patient_id || visibleIds[0] || 'q1b'
  const patientIds = visibleIds.length ? [...new Set(visibleIds)] : [patientId]
  const patientRoles = buildPatientRoles(userConfig)

  // replaceUserSession to avoid deep-merge accumulating roles array
  await replaceUserSession(event, {
    user: {
      email,
      name: session.user.name,
      picture: session.user.picture,
      roles,
      activeRole: roles[0],
      phone: userConfig.phone || null,
      patientId,
      patientIds,
      patientRoles,
    },
  })
})
