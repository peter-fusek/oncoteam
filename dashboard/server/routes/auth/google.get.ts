import { getRoleMapSync, visiblePatientIds } from '../../utils/access-rights'

export default defineOAuthGoogleEventHandler({
  config: {
    scope: ['openid', 'email', 'profile'],
  },
  async onSuccess(event, { user }) {
    const config = useRuntimeConfig()
    const allowed = config.allowedEmails.split(',').map((e: string) => e.trim())

    if (!allowed.includes(user.email)) {
      throw createError({ statusCode: 403, message: 'Not authorized' })
    }

    const roleMap = getRoleMapSync()
    const userConfig = roleMap[user.email]
    // #442 red-team finding — fail closed on missing role-map entry.
    // Previously silently fell back to { roles: ['advocate'], patient_id: 'q1b' }
    // — so any Google account in NUXT_ALLOWED_EMAILS but demoted / never
    // added to NUXT_ROLE_MAP got Erika's full clinical view. Classic
    // silent-fallback class (#436 / #438 / #440 Patterns A+C) that the
    // Sprints 98-100 sweep missed in the Nuxt middleware layer.
    if (!userConfig) {
      throw createError({
        statusCode: 403,
        message: 'No patient access configured for this account. Contact your administrator.',
      })
    }
    const roles = userConfig.roles || ['advocate']
    // Patient scoping: no silent q1b fallback; userConfig must explicitly
    // carry patient_id(s) via patient_roles (new #422 shape) or patient_ids.
    const visibleIds = [...new Set(visiblePatientIds(userConfig))]
    if (visibleIds.length === 0) {
      throw createError({
        statusCode: 403,
        message: 'No patient access configured for this account. Contact your administrator.',
      })
    }
    const patientId = userConfig.patient_id || visibleIds[0]
    const patientIds = visibleIds

    await setUserSession(event, {
      user: {
        email: user.email,
        name: user.name,
        picture: user.picture,
        roles,
        activeRole: roles[0],
        phone: userConfig.phone || null,
        patientId,
        patientIds,
      },
    })

    // Redirect to role-appropriate landing page
    const landingPages: Record<string, string> = {
      advocate: '/',
      patient: '/patient',
      doctor: '/labs',
    }

    return sendRedirect(event, landingPages[roles[0]] || '/')
  },
})
