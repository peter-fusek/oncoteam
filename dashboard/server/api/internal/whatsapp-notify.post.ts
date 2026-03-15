import twilio from 'twilio'

/**
 * Internal WhatsApp notify endpoint for server-to-server calls.
 * Uses DASHBOARD_API_KEY auth instead of session auth.
 * Sends a message to all configured phone numbers in NUXT_ROLE_MAP.
 */
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()

  // API key auth (same as oncoteam backend uses for dashboard API)
  const auth = getHeader(event, 'authorization')
  const apiKey = config.public?.oncoteamApiKey || ''
  if (!auth || !apiKey || auth !== `Bearer ${apiKey}`) {
    throw createError({ statusCode: 401, message: 'Invalid API key' })
  }

  const { message } = await readBody(event)
  if (!message || typeof message !== 'string') {
    throw createError({ statusCode: 400, message: 'Message is required' })
  }

  if (!config.twilioAccountSid || !config.twilioAuthToken || !config.twilioWhatsappFrom) {
    throw createError({ statusCode: 500, message: 'WhatsApp not configured' })
  }

  // Get all phone numbers from roleMap
  let roleMap: Record<string, { roles?: string[]; phone?: string }> = {}
  try {
    const raw = config.roleMap
    roleMap = typeof raw === 'string' ? JSON.parse(raw || '{}') : (raw as typeof roleMap) || {}
  } catch {
    roleMap = {}
  }

  const phones = new Set<string>()
  for (const entry of Object.values(roleMap)) {
    if (entry.phone) phones.add(entry.phone)
  }

  if (phones.size === 0) {
    return { ok: false, error: 'No phone numbers configured in NUXT_ROLE_MAP' }
  }

  const client = twilio(config.twilioAccountSid, config.twilioAuthToken)
  const results: Array<{ phone: string; sid?: string; error?: string }> = []

  const sanitized = message.slice(0, 1500).trim()

  for (const phone of phones) {
    try {
      const result = await client.messages.create({
        from: config.twilioWhatsappFrom,
        to: `whatsapp:${phone}`,
        body: sanitized,
      })
      results.push({ phone, sid: result.sid })
    } catch (err) {
      results.push({ phone, error: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  return { ok: true, sent: results.length, results }
})
