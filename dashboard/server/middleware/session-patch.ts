/**
 * Server middleware to patch stale sessions from pre-Sprint 17.
 * Sessions created before role support lack `roles`, `activeRole`, and `phone`.
 * This patches them on-the-fly using the roleMap config so users don't need to re-login.
 */
export default defineEventHandler(async (event) => {
  // Only patch page requests, not API calls or static assets
  const path = getRequestURL(event).pathname
  if (path.startsWith('/api/') || path.startsWith('/_nuxt/') || path.startsWith('/__nuxt')) return

  const session = await getUserSession(event)
  if (!session.user?.email) return
  // Skip if session is fully patched AND patientIds has no duplicates
  const existingIds = session.user.patientIds as string[] | undefined
  const hasDuplicates = existingIds && existingIds.length !== new Set(existingIds).size
  if (session.user.roles && Array.isArray(session.user.roles) && session.user.patientId && existingIds && !hasDuplicates) return

  const config = useRuntimeConfig()
  let roleMap: Record<string, { roles?: string[]; phone?: string; patient_id?: string; patient_ids?: string[] }> = {}
  try {
    // Nuxt may auto-parse JSON env vars into objects
    const raw = config.roleMap
    roleMap = typeof raw === 'string' ? JSON.parse(raw || '{}') : (raw as typeof roleMap) || {}
  } catch (e) {
    console.warn('[session-patch] Failed to parse roleMap:', e)
    roleMap = {}
  }

  const email = session.user.email as string
  const userConfig = roleMap[email] || { roles: ['advocate'] }
  const roles = userConfig.roles || ['advocate']

  const patientId = userConfig.patient_id || 'erika'
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
