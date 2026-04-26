import { getRoleMapSync } from '../../utils/access-rights'

export default defineOAuthGoogleEventHandler({
  config: {
    scope: ['openid', 'email', 'profile'],
  },
  async onSuccess(event, { user }) {
    // NUXT_ROLE_MAP is the single auth gate (NUXT_ALLOWED_EMAILS was deprecated
    // in Sprint 101 and removed from Railway env). No silent fallback to
    // advocate/q1b — unknown emails get 403, fail-closed (matches #443 P0 fix).
    const roleMap = getRoleMapSync()
    const userConfig = roleMap[user.email]

    if (!userConfig) {
      throw createError({ statusCode: 403, message: 'Not authorized' })
    }

    const roles = userConfig.roles || ['advocate']
    // Patient scoping: advocate sees all patient_ids, others see only their own
    const patientId = userConfig.patient_id || 'q1b'
    const patientIds = [...new Set(userConfig.patient_ids || [patientId])]

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
