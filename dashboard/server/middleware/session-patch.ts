/**
 * Server middleware to patch stale sessions from pre-Sprint 17.
 * Sessions created before role support lack `roles`, `activeRole`, and `phone`.
 * This patches them on-the-fly using the roleMap so users don't need to re-login.
 */
import { getRoleMapSync } from '../utils/access-rights'

export default defineEventHandler(async (event) => {
  // Only patch page requests, not API calls or static assets.
  // /auth/ excluded per Felix #447: H3 sendRedirect resolves to undefined which
  // H3 treats as "continue chain", so the OAuth handler was firing AFTER this
  // middleware closed the response socket — accumulating in-flight contexts
  // and unresolvable Google HTTPS connections under load.
  const path = getRequestURL(event).pathname
  if (
    path.startsWith('/api/')
    || path.startsWith('/_nuxt/')
    || path.startsWith('/__nuxt')
    || path.startsWith('/auth/')
  ) return

  const session = await getUserSession(event)
  if (!session.user?.email) return
  // Skip if session is fully patched AND patientIds matches roleMap
  const existingIds = session.user.patientIds as string[] | undefined
  const hasDuplicates = existingIds && existingIds.length !== new Set(existingIds).size
  // Re-patch when roleMap patient_ids changed (e.g. new patient added)
  let roleMapChanged = false
  try {
    const rm = getRoleMapSync()
    const email = session.user.email as string
    const uc = rm[email]
    if (uc?.patient_ids) {
      const expected = [...new Set(uc.patient_ids)]
      roleMapChanged = !existingIds || existingIds.length !== expected.length || !expected.every((id: string) => existingIds.includes(id))
    }
  } catch { /* re-patch on parse error */ }
  if (!roleMapChanged && session.user.roles && Array.isArray(session.user.roles) && session.user.patientId && existingIds && !hasDuplicates) return

  const roleMap = getRoleMapSync()

  const email = session.user.email as string
  const userConfig = roleMap[email] || { roles: ['advocate'] }
  const roles = userConfig.roles || ['advocate']

  const patientId = userConfig.patient_id || 'q1b'
  const patientIds = [...new Set(userConfig.patient_ids || [patientId])]

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
    },
  })
})
