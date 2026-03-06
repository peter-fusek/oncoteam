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
