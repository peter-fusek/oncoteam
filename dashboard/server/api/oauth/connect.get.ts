import { resolveOAuthToken } from '../../utils/oauth-tokens'

const ONCOFILES_URL = process.env.NUXT_ONCOFILES_PUBLIC_URL || 'https://oncofiles.com'

export default defineEventHandler((event) => {
  const query = getQuery(event)
  const token = String(query.token || '')

  if (!token) {
    setResponseStatus(event, 400)
    return { error: 'Missing token parameter' }
  }

  const patientId = resolveOAuthToken(token)
  if (!patientId) {
    setResponseStatus(event, 410)
    return { error: 'Token expired or invalid. Please request a new link via WhatsApp.' }
  }

  return sendRedirect(event, `${ONCOFILES_URL}/oauth/authorize/drive?patient_id=${encodeURIComponent(patientId)}`)
})
