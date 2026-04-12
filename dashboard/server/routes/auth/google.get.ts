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

    let roleMap: Record<string, { roles?: string[]; phone?: string; patient_id?: string; patient_ids?: string[] }> = {}
    try {
      const raw = config.roleMap
      roleMap = typeof raw === 'string' ? JSON.parse(raw || '{}') : (raw as typeof roleMap) || {}
    }
    catch {
      roleMap = {}
    }
    const userConfig = roleMap[user.email] || { roles: ['advocate'] }
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
