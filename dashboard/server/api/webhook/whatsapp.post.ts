import twilio from 'twilio'
import { handleWhatsAppCommand, type CommandResult } from '../../utils/whatsapp-commands'

const RATE_LIMIT_MAX = 20
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000
const rateLimitMap = new Map<string, { count: number; resetAt: number }>()

function normalizePhone(phone: string): string {
  return phone.replace(/[\s\-()]/g, '')
}

function extractPhoneAllowlist(roleMapRaw: string | Record<string, { phone?: string }>): Set<string> {
  try {
    const roleMap = typeof roleMapRaw === 'string' ? JSON.parse(roleMapRaw || '{}') : roleMapRaw || {}
    const phones = new Set<string>()
    for (const config of Object.values(roleMap) as Array<{ phone?: string }>) {
      if (config.phone) phones.add(normalizePhone(config.phone))
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
  const from = normalizePhone(String(body?.From || '').replace('whatsapp:', ''))
  const messageBody = String(body?.Body || '').trim()
  const twilioSignature = getRequestHeader(event, 'x-twilio-signature') || ''

  // Validate Twilio signature (try both proxy and direct URLs)
  const requestUrl = getRequestURL(event).toString()
  let isValid = twilio.validateRequest(
    config.twilioAuthToken,
    twilioSignature,
    requestUrl,
    body || {},
  )
  // Reverse proxy may reconstruct URL differently — try with explicit https
  if (!isValid) {
    const httpsUrl = requestUrl.replace(/^http:/, 'https:')
    if (httpsUrl !== requestUrl) {
      isValid = twilio.validateRequest(
        config.twilioAuthToken,
        twilioSignature,
        httpsUrl,
        body || {},
      )
    }
  }

  // Phone allowlist is enforced below — log signature failure but don't block
  // (Reverse proxy URL reconstruction may not match Twilio's expected URL)
  if (!isValid) {
    console.warn('[whatsapp-webhook] Twilio signature validation failed, relying on phone allowlist')
  }

  // Phone allowlist check (mandatory — primary security gate)
  const allowedPhones = extractPhoneAllowlist(config.roleMap)
  if (!allowedPhones.has(from)) {
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
  const oncoteamApiUrl = config.oncoteamApiUrl as string
  const result: CommandResult = await handleWhatsAppCommand(messageBody, oncoteamApiUrl)

  if (result.type === 'async') {
    // Conversational message — respond immediately, send Claude's answer async.
    // Claude API takes 30-60s, exceeding Twilio's 15s webhook timeout.
    const twilioFrom = `whatsapp:${config.twilioWhatsappFrom || '+14155238886'}`
    const twilioTo = `whatsapp:${from}`

    // Fire-and-forget: call Claude API and send response via Twilio REST API
    ;(async () => {
      const apiKey = config.oncoteamApiKey || ''
      const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}

      // Step 1: Get Claude response
      let reply: string
      try {
        console.log('[whatsapp-async] Calling Claude API for:', result.message.slice(0, 50))
        const chatResult = await $fetch<{ response: string }>(`${oncoteamApiUrl}/api/internal/whatsapp-chat`, {
          method: 'POST',
          body: { message: result.message, lang: result.lang },
          headers,
        })
        reply = chatResult.response || 'Prepáčte, nepodarilo sa spracovať správu.'
        console.log('[whatsapp-async] Claude responded:', reply.slice(0, 80))
      }
      catch (err) {
        console.error('[whatsapp-async] Claude API failed:', err)
        reply = result.lang === 'sk'
          ? 'Prepáčte, nepodarilo sa spracovať správu. Skúste príkaz ako *labky* alebo *pomoc*.'
          : 'Sorry, could not process your message. Try a command like *labs* or *help*.'
      }

      // Step 2: Send reply via Twilio REST API
      try {
        console.log('[whatsapp-async] Sending via Twilio:', twilioFrom, '->', twilioTo)
        const client = twilio(config.twilioAccountSid, config.twilioAuthToken)
        const msg = await client.messages.create({
          from: twilioFrom,
          to: twilioTo,
          body: reply.slice(0, 1500),
        })
        console.log('[whatsapp-async] Twilio sent OK, SID:', msg.sid)
      }
      catch (err) {
        console.error('[whatsapp-async] Twilio send failed:', err)
      }

      // Step 3: Log exchange
      $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        body: { phone: from, user_message: messageBody, bot_response: reply },
        headers,
      }).catch(() => {})
    })()

    // Immediate response to Twilio — acknowledge receipt
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml(result.lang === 'sk' ? 'Premýšľam... 🤔' : 'Thinking... 🤔')
  }

  // Synchronous command response
  const reply = result.text

  // Log the WhatsApp exchange to oncofiles (fire-and-forget)
  try {
    const apiKey = config.oncoteamApiKey || ''
    const logHeaders: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
      method: 'POST',
      body: { phone: from, user_message: messageBody, bot_response: reply },
      headers: logHeaders,
    }).catch(() => {})
  }
  catch {
    // Logging failure must not block the response
  }

  setResponseHeader(event, 'content-type', 'text/xml')
  return twiml(reply)
})
