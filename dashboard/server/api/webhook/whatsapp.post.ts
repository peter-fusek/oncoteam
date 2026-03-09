import twilio from 'twilio'
import { handleWhatsAppCommand } from '../../utils/whatsapp-commands'

const RATE_LIMIT_MAX = 20
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000
const rateLimitMap = new Map<string, { count: number; resetAt: number }>()

function extractPhoneAllowlist(roleMapJson: string): Set<string> {
  try {
    const roleMap = JSON.parse(roleMapJson || '{}')
    const phones = new Set<string>()
    for (const config of Object.values(roleMap) as Array<{ phone?: string }>) {
      if (config.phone) phones.add(config.phone)
    }
    return phones
  }
  catch {
    return new Set()
  }
}

function twiml(message: string): string {
  const escaped = message
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return `<?xml version="1.0" encoding="UTF-8"?><Response><Message>${escaped}</Message></Response>`
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()

  if (!config.twilioAccountSid || !config.twilioAuthToken) {
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('WhatsApp not configured.')
  }

  // Parse form-encoded body from Twilio
  const body = await readBody(event)
  const from = String(body?.From || '').replace('whatsapp:', '')
  const messageBody = String(body?.Body || '').trim()
  const twilioSignature = getRequestHeader(event, 'x-twilio-signature') || ''

  // Validate Twilio signature
  const requestUrl = getRequestURL(event).toString()
  const isValid = twilio.validateRequest(
    config.twilioAuthToken,
    twilioSignature,
    requestUrl,
    body || {},
  )

  if (!isValid) {
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Unauthorized.')
  }

  // Phone allowlist check
  const allowedPhones = extractPhoneAllowlist(config.roleMap)
  if (allowedPhones.size > 0 && !allowedPhones.has(from)) {
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Your phone number is not registered.')
  }

  // Rate limiting per phone
  const now = Date.now()
  const rateEntry = rateLimitMap.get(from)
  if (rateEntry && now < rateEntry.resetAt) {
    if (rateEntry.count >= RATE_LIMIT_MAX) {
      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml('Rate limit exceeded. Try again later.')
    }
    rateEntry.count++
  }
  else {
    rateLimitMap.set(from, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS })
  }

  // Process command and respond
  const oncoteamApiUrl = config.public.oncoteamApiUrl as string
  const reply = await handleWhatsAppCommand(messageBody, oncoteamApiUrl)

  setResponseHeader(event, 'content-type', 'text/xml')
  return twiml(reply)
})
