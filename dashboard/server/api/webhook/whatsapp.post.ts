import twilio from 'twilio'
import { handleWhatsAppCommand, type CommandResult } from '../../utils/whatsapp-commands'
import { getOnboardingState, setOnboardingState, isOnboarding, getActiveSessionCount } from '../../utils/onboarding-state'
import { handleOnboardingMessage } from '../../utils/onboarding-handler'
import { isApproved, checkApprovedWithBackend, resolvePatientIdFromPhone, setPhonePatient, getAllowedPatientIdsForPhone, getActivePatientForPhone } from '../../utils/approved-phones'
import { recordInbound, sendWhatsApp } from '../../utils/twilio-send'
import type { OnboardingState } from '../../utils/onboarding-state'

const RATE_LIMIT_MAX = 20
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000
const rateLimitMap = new Map<string, { count: number; resetAt: number }>()
const MAX_MEDIA_ATTACHMENTS = 3

function mimeToExt(contentType: string): string {
  const map: Record<string, string> = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'application/pdf': 'pdf',
  }
  return map[contentType] || 'bin'
}

function generateMediaFilename(contentType: string): string {
  const now = new Date()
  const ts = now.toISOString().replace(/[-:T]/g, '').replace(/\..+/, '').slice(0, 15)
  return `whatsapp_${ts}.${mimeToExt(contentType)}`
}

interface MediaAttachment {
  url: string
  contentType: string
}

function extractMedia(body: Record<string, unknown>): MediaAttachment[] {
  const numMedia = parseInt(String(body?.NumMedia || '0'), 10)
  if (numMedia <= 0) return []

  const attachments: MediaAttachment[] = []
  const count = Math.min(numMedia, MAX_MEDIA_ATTACHMENTS)
  for (let i = 0; i < count; i++) {
    const url = String(body?.[`MediaUrl${i}`] || '')
    const contentType = String(body?.[`MediaContentType${i}`] || '')
    if (url && contentType) {
      attachments.push({ url, contentType })
    }
  }
  return attachments
}

const TWILIO_MEDIA_DOMAINS = ['https://api.twilio.com/', 'https://media.twiliocdn.com/']

async function downloadTwilioMedia(
  mediaUrl: string,
  accountSid: string,
  authToken: string,
): Promise<ArrayBuffer> {
  // SSRF protection: only fetch from Twilio domains
  if (!TWILIO_MEDIA_DOMAINS.some(d => mediaUrl.startsWith(d))) {
    throw new Error(`Untrusted media URL domain: ${mediaUrl}`)
  }
  const auth = Buffer.from(`${accountSid}:${authToken}`).toString('base64')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch(mediaUrl, {
      headers: { Authorization: `Basic ${auth}` },
      redirect: 'follow',
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(`Failed to download media: ${response.status} ${response.statusText}`)
    }
    return response.arrayBuffer()
  } finally {
    clearTimeout(timeout)
  }
}

function normalizePhone(phone: string): string {
  return phone.replace(/[\s\-()]/g, '')
}

function isValidPhoneFormat(phone: string): boolean {
  return /^\+[1-9]\d{6,14}$/.test(phone)
}

function extractPhoneAllowlist(roleMapRaw: string | Record<string, { phone?: string; patient_id?: string; roles?: string[] }>): Set<string> {
  try {
    const roleMap = typeof roleMapRaw === 'string' ? JSON.parse(roleMapRaw || '{}') : roleMapRaw || {}
    const phones = new Set<string>()
    const entries = Object.values(roleMap) as Array<{ phone?: string; patient_id?: string; roles?: string[] }>
    // Two-pass: advocates first so their patient_id takes priority for shared phones
    const advocates = entries.filter(c => c.roles?.includes('advocate'))
    const others = entries.filter(c => !c.roles?.includes('advocate'))
    for (const config of [...advocates, ...others]) {
      if (config.phone) {
        const normalized = normalizePhone(config.phone)
        phones.add(normalized)
        // First-wins: don't overwrite if phone already mapped by a higher-priority entry
        if (config.patient_id && !resolvePatientIdFromPhone(normalized)) {
          setPhonePatient(normalized, config.patient_id)
        }
      }
    }
    return phones
  }
  catch (err) {
    console.error('[whatsapp-webhook] CRITICAL: Failed to parse role map — all users locked out:', err)
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

  // Phone format validation — reject malformed senders
  if (!isValidPhoneFormat(from)) {
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Invalid sender.')
  }

  // Record inbound for 24h session window tracking (template vs free-form)
  recordInbound(from)

  // Rate limiting per phone — applied BEFORE onboarding to prevent abuse
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

  // Phone allowlist check (mandatory — primary security gate)
  const allowedPhones = extractPhoneAllowlist(config.roleMap)
  let isAllowed = allowedPhones.has(from) || isApproved(from)

  // If not in local cache, double-check with backend (oncofiles-persisted phones)
  if (!isAllowed) {
    const oncoteamUrl = config.oncoteamApiUrl as string
    const apiKey = (config.oncoteamApiKey || '') as string
    isAllowed = await checkApprovedWithBackend(from, oncoteamUrl, apiKey)
  }

  if (!isAllowed) {
    // Cap total active onboarding sessions to prevent resource exhaustion
    const MAX_ACTIVE_SESSIONS = 10
    if (!isOnboarding(from) && getActiveSessionCount() >= MAX_ACTIVE_SESSIONS) {
      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml('Service is busy. Please try again later.')
    }

    // Check if user is in onboarding flow
    if (isOnboarding(from)) {
      // Handle media from onboarding users with a patient_id
      const onboardingMedia = extractMedia(body)
      const onboardingState = getOnboardingState(from)
      if (onboardingMedia.length > 0 && onboardingState?.patientId) {
        const oncoteamUrl = config.oncoteamApiUrl as string
        const apiKey = (config.oncoteamApiKey || '') as string
        const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
        const rawFrom = String(config.twilioWhatsappFrom || '')
        if (!rawFrom) { console.error('[whatsapp] NUXT_TWILIO_WHATSAPP_FROM not configured'); return twiml('Configuration error.') }
        const twilioFrom = rawFrom.startsWith('whatsapp:') ? rawFrom : `whatsapp:${rawFrom}`
        const twilioTo = `whatsapp:${from}`

        ;(async () => {
          const results: string[] = []
          for (const media of onboardingMedia) {
            try {
              const arrayBuffer = await downloadTwilioMedia(
                media.url,
                config.twilioAccountSid as string,
                config.twilioAuthToken as string,
              )
              const base64 = Buffer.from(arrayBuffer).toString('base64')
              const filename = generateMediaFilename(media.contentType)

              const mediaResult = await $fetch<{ status: string; document_id: string; summary: string }>(
                `${oncoteamUrl}/api/internal/whatsapp-media`,
                {
                  method: 'POST',
                  body: {
                    media_base64: base64,
                    content_type: media.contentType,
                    filename,
                    phone: from,
                    patient_id: onboardingState.patientId,
                  },
                  headers,
                },
              )
              results.push(mediaResult.summary || 'Dokument bol nahraný.')
            }
            catch (err) {
              console.error('[whatsapp-media-onboarding] Failed:', err)
              results.push('Chyba pri spracovaní prílohy.')
            }
          }

          try {
            const client = twilio(config.twilioAccountSid, config.twilioAuthToken)
            await client.messages.create({
              from: twilioFrom,
              to: twilioTo,
              body: results.join('\n\n').slice(0, 1500),
            })
          }
          catch (err) {
            console.error('[whatsapp-media-onboarding] Twilio send failed:', err)
          }
        })()

        setResponseHeader(event, 'content-type', 'text/xml')
        return twiml('Spracovávam dokument... 📄')
      }

      const oncoteamUrl = config.oncoteamApiUrl as string
      const apiKey = (config.oncoteamApiKey || '') as string
      const onboardingResult = await handleOnboardingMessage(from, messageBody, oncoteamUrl, apiKey)
      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml(onboardingResult.text || '')
    }

    // Start onboarding for unknown phone numbers
    const now = Date.now()
    const initialState: OnboardingState = {
      step: 'welcome',
      phone: from,
      lang: 'sk',
      createdAt: now,
      updatedAt: now,
    }
    setOnboardingState(from, initialState)

    const oncoteamUrl = config.oncoteamApiUrl as string
    const apiKey = (config.oncoteamApiKey || '') as string
    const onboardingResult = await handleOnboardingMessage(from, messageBody, oncoteamUrl, apiKey)
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml(onboardingResult.text || '')
  }

  // ── Media attachment handling ──────────────────────────────────────
  const mediaAttachments = extractMedia(body)
  if (mediaAttachments.length > 0) {
    const oncoteamUrl = config.oncoteamApiUrl as string
    const apiKey = (config.oncoteamApiKey || '') as string
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const rawFrom = String(config.twilioWhatsappFrom || '')
    if (!rawFrom) { console.error('[whatsapp] NUXT_TWILIO_WHATSAPP_FROM not configured'); return twiml('Configuration error.') }
    const twilioFrom = rawFrom.startsWith('whatsapp:') ? rawFrom : `whatsapp:${rawFrom}`
    const twilioTo = `whatsapp:${from}`

    // Fire-and-forget: download, upload, analyze, respond via Twilio REST
    ;(async () => {
      const results: string[] = []
      for (const media of mediaAttachments) {
        try {
          const arrayBuffer = await downloadTwilioMedia(
            media.url,
            config.twilioAccountSid as string,
            config.twilioAuthToken as string,
          )
          const base64 = Buffer.from(arrayBuffer).toString('base64')
          const filename = generateMediaFilename(media.contentType)

          const result = await $fetch<{ status: string; document_id: string; summary: string }>(
            `${oncoteamUrl}/api/internal/whatsapp-media`,
            {
              method: 'POST',
              body: {
                media_base64: base64,
                content_type: media.contentType,
                filename,
                phone: from,
                patient_id: getActivePatientForPhone(from),
              },
              headers,
            },
          )
          const summary = result.summary || 'Dokument bol nahraný.'
          results.push(`${filename}: ${summary}`)
        }
        catch (err) {
          console.error('[whatsapp-media] Failed to process attachment:', err)
          results.push('Chyba pri spracovaní prílohy.')
        }
      }

      // Send results via Twilio REST
      const reply = results.join('\n\n').slice(0, 1500)
      try {
        const client = twilio(config.twilioAccountSid, config.twilioAuthToken)
        await client.messages.create({
          from: twilioFrom,
          to: twilioTo,
          body: reply,
        })
      }
      catch (err) {
        console.error('[whatsapp-media] Twilio send failed:', err)
      }

      // Log the exchange
      $fetch(`${oncoteamUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        body: { phone: from, user_message: `[media x${mediaAttachments.length}] ${messageBody}`, bot_response: reply },
        headers,
      }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
    })()

    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Spracovávam dokument... 📄')
  }

  // Process command and respond
  const oncoteamApiUrl = config.oncoteamApiUrl as string
  const allowedPatientIds = getAllowedPatientIdsForPhone(from, config.roleMap as string)
  const whatsappPatientId = getActivePatientForPhone(from)
  const hasMultiplePatients = allowedPatientIds.length > 1
  const result: CommandResult = await handleWhatsAppCommand(messageBody, oncoteamApiUrl, from, { patientId: whatsappPatientId, allowedPatientIds, hasMultiplePatients })

  if (result.type === 'async') {
    // Conversational message — respond immediately, send Claude's answer async.
    // Claude API takes 30-60s, exceeding Twilio's 15s webhook timeout.

    // Fire-and-forget: call Claude API and send response via Twilio REST API
    ;(async () => {
      const apiKey = config.oncoteamApiKey || ''
      const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}

      // Step 1: Get Claude response (55s timeout — generous for autonomous agent)
      let reply: string
      try {
        console.log('[whatsapp-async] Calling Claude API for:', result.message.slice(0, 50))
        const chatResult = await $fetch<{ response: string }>(`${oncoteamApiUrl}/api/internal/whatsapp-chat`, {
          method: 'POST',
          body: { message: result.message, lang: result.lang, phone: from, patient_id: whatsappPatientId },
          headers,
          signal: AbortSignal.timeout(55_000),
        })
        reply = chatResult.response || 'Prepáčte, nepodarilo sa spracovať správu.'
        console.log('[whatsapp-async] Claude responded:', reply.slice(0, 80))
      }
      catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err)
        console.error('[whatsapp-async] Claude API failed:', errMsg)
        reply = result.lang === 'sk'
          ? 'Prepáčte, nepodarilo sa spracovať správu. Skúste príkaz ako *labky* alebo *pomoc*.'
          : 'Sorry, could not process your message. Try a command like *labs* or *help*.'
      }

      // Step 2: Send reply via shared twilio-send utility
      const sendResult = await sendWhatsApp({ to: from, body: reply })
      if (sendResult.ok) {
        console.log('[whatsapp-async] Twilio sent OK, SID:', sendResult.sid)
      }
      else {
        console.error('[whatsapp-async] Twilio send failed:', sendResult.error)
      }

      // Step 3: Log exchange
      $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        body: { phone: from, user_message: messageBody, bot_response: reply },
        headers,
      }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
    })()

    // Immediate response to Twilio — acknowledge receipt
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml(result.lang === 'sk' ? 'Premýšľam... (~30s) 🤔' : 'Thinking... (~30s) 🤔')
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
    }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
  }
  catch {
    // Logging failure must not block the response
  }

  setResponseHeader(event, 'content-type', 'text/xml')
  return twiml(reply)
})
