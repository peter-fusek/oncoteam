const VALID_ROLES = ['advocate', 'patient', 'doctor'] as const

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }
  const { role } = await readBody(event)
  if (typeof role !== 'string' || !VALID_ROLES.includes(role as typeof VALID_ROLES[number])) {
    throw createError({ statusCode: 400, message: 'Invalid role' })
  }
  if (!session.user.roles?.includes(role)) {
    throw createError({ statusCode: 403, message: 'Role not assigned' })
  }
  await replaceUserSession(event, {
    user: { ...session.user, activeRole: role },
  })
  return { ok: true, activeRole: role }
})
