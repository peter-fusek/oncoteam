export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }
  const { role } = await readBody(event)
  if (!session.user.roles?.includes(role)) {
    throw createError({ statusCode: 403, message: 'Role not assigned' })
  }
  await setUserSession(event, {
    user: { ...session.user, activeRole: role },
  })
  return { ok: true, activeRole: role }
})
