import { getRoleMapSync, visiblePatientIds } from '../../utils/access-rights'

export default defineOAuthGoogleEventHandler({
  config: {
    scope: ['openid', 'email', 'profile'],
  },
  async onSuccess(event, { user }) {
    // #443 / Phase D — NUXT_ROLE_MAP is now the SOLE source of truth for
    // who can sign in. The previous dual-list architecture (
    // NUXT_ALLOWED_EMAILS gate + NUXT_ROLE_MAP scope) let the two drift
    // out of sync — e.g. peter.fusek@instarea.com was in allowedEmails
    // but never in role_map, and the pre-fix silent fallback granted it
    // Erika's session on every sign-in. Collapsing to a single list
    // removes that class of bug: if your email has a role_map entry,
    // you can sign in; otherwise 403.
    const roleMap = getRoleMapSync()
    const userConfig = roleMap[user.email]
    if (!userConfig) {
      console.warn(
        `[auth/google] Sign-in rejected: no NUXT_ROLE_MAP entry for ${user.email}`,
      )
      // #443 Phase E — dedicated landing page instead of silent bounce
      // or generic 403 error boundary. The page explains who to contact.
      return sendRedirect(
        event,
        `/auth/forbidden?email=${encodeURIComponent(user.email)}`,
      )
    }
    const roles = userConfig.roles || ['advocate']
    // Patient scoping: no silent q1b fallback; userConfig must explicitly
    // carry patient_id(s) via patient_roles (new #422 shape) or patient_ids.
    const visibleIds = [...new Set(visiblePatientIds(userConfig))]
    if (visibleIds.length === 0) {
      console.warn(
        `[auth/google] Sign-in rejected: role_map entry for ${user.email} has no patient scope`,
      )
      return sendRedirect(
        event,
        `/auth/forbidden?email=${encodeURIComponent(user.email)}`,
      )
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
