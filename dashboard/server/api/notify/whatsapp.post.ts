import twilio from 'twilio'

const RATE_LIMIT_MAX = 10
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000 // 1 hour
const MAX_MESSAGE_LENGTH = 2000
const rateLimitMap = new Map<string, { count: number; resetAt: number }>()

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }

  // Rate limiting per user
  const userKey = session.user.email as string
  const now = Date.now()
  const rateEntry = rateLimitMap.get(userKey)
  if (rateEntry && now < rateEntry.resetAt) {
    if (rateEntry.count >= RATE_LIMIT_MAX) {
      throw createError({ statusCode: 429, message: 'Rate limit exceeded. Try again later.' })
    }
    rateEntry.count++
  } else {
    rateLimitMap.set(userKey, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS })
  }

  const config = useRuntimeConfig()
  const body = await readBody(event)
  const message = body.message
  const patientName = (body.patient_name as string | undefined)?.trim() || 'Patient'

  if (!message || typeof message !== 'string') {
    throw createError({ statusCode: 400, message: 'Message is required' })
  }

  // Only send to the user's own phone from session (no arbitrary recipients)
  const phone = session.user.phone as string | undefined
  if (!phone) {
    throw createError({ statusCode: 400, message: 'No phone number configured for your account' })
  }

  if (!config.twilioAccountSid || !config.twilioAuthToken || !config.twilioWhatsappFrom) {
    throw createError({ statusCode: 500, message: 'WhatsApp not configured' })
  }

  // Sanitize message: trim, cap length, strip control chars (keep newlines)
  const sanitized = message
    .slice(0, MAX_MESSAGE_LENGTH)
    .replace(/[^\P{C}\n\r\t]/gu, '')
    .trim()

  if (!sanitized) {
    throw createError({ statusCode: 400, message: 'Message is empty after sanitization' })
  }

  const roleName = session.user.activeRole || 'advocate'
  const userName = session.user.name || session.user.email
  const fullMessage = `Oncoteam Update\nPatient: ${patientName} | For: ${userName} (${roleName})\n---\n${sanitized}`

  const client = twilio(config.twilioAccountSid, config.twilioAuthToken)

  const result = await client.messages.create({
    from: config.twilioWhatsappFrom,
    to: `whatsapp:${phone}`,
    body: fullMessage,
  })

  return { ok: true, sid: result.sid }
})
