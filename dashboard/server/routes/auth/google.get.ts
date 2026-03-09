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

    let roleMap: Record<string, { roles?: string[]; phone?: string }> = {}
    try {
      const raw = config.roleMap
      roleMap = typeof raw === 'string' ? JSON.parse(raw || '{}') : (raw as typeof roleMap) || {}
    } catch {
      roleMap = {}
    }
    const userConfig = roleMap[user.email] || { roles: ['advocate'] }
    const roles = userConfig.roles || ['advocate']

    await setUserSession(event, {
      user: {
        email: user.email,
        name: user.name,
        picture: user.picture,
        roles,
        activeRole: roles[0],
        phone: userConfig.phone || null,
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
