import { broadcastWhatsApp } from '../../utils/twilio-send'

/**
 * Internal WhatsApp notify endpoint for server-to-server calls.
 * Uses DASHBOARD_API_KEY auth instead of session auth.
 * Sends a message to all configured phone numbers in NUXT_ROLE_MAP.
 */
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()

  // API key auth (same as oncoteam backend uses for dashboard API)
  const auth = getHeader(event, 'authorization')
  const apiKey = config.oncoteamApiKey || ''
  if (!auth || !apiKey || auth !== `Bearer ${apiKey}`) {
    throw createError({ statusCode: 401, message: 'Invalid API key' })
  }

  const body = await readBody(event)
  const message = body.message
  if (!message || typeof message !== 'string') {
    throw createError({ statusCode: 400, message: 'Message is required' })
  }

  const sanitized = message.slice(0, 1500).trim()
  if (!sanitized) {
    throw createError({ statusCode: 400, message: 'Message is empty after sanitization' })
  }

  const templateKey = body.template_key as string | undefined
  const templateVars = body.template_vars as Record<string, string> | undefined

  const results = await broadcastWhatsApp(sanitized, templateKey, templateVars)

  if (results.length === 0) {
    return { ok: false, error: 'No phone numbers configured in NUXT_ROLE_MAP' }
  }

  return { ok: true, sent: results.length, results }
})
