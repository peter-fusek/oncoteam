export default defineOAuthGoogleEventHandler({
  config: {
    scope: ['openid', 'email', 'profile'],
    authorizationParams: {
      // Skip account chooser — auto-select the allowed Google account
      login_hint: 'peterfusek1980@gmail.com',
    },
  },
  async onSuccess(event, { user }) {
    const config = useRuntimeConfig()
    const allowed = config.allowedEmails.split(',').map((e: string) => e.trim())

    if (!allowed.includes(user.email)) {
      throw createError({ statusCode: 403, message: 'Not authorized' })
    }

    await setUserSession(event, {
      user: {
        email: user.email,
        name: user.name,
        picture: user.picture,
      },
    })

    return sendRedirect(event, '/')
  },
})
