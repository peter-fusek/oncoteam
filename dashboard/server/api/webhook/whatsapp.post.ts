import twilio from 'twilio'
import { appendMedicalDisclaimer, handleWhatsAppCommand, type CommandResult } from '../../utils/whatsapp-commands'
import { getOnboardingState, setOnboardingState, isOnboarding, getActiveSessionCount } from '../../utils/onboarding-state'
import { handleOnboardingMessage } from '../../utils/onboarding-handler'
import { isApproved, checkApprovedWithBackend, resolvePatientIdFromPhone, setPhonePatient, getAllowedPatientIdsForPhone, getActivePatientForPhone, getUserInfoForPhone } from '../../utils/approved-phones'
import { recordInbound, sendWhatsApp } from '../../utils/twilio-send'
import { getRoleMap } from '../../utils/access-rights'
import type { OnboardingState } from '../../utils/onboarding-state'

const RATE_LIMIT_MAX = 20
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000
const rateLimitMap = new Map<string, { count: number; resetAt: number }>()
const MAX_MEDIA_ATTACHMENTS = 3

// Patient name map cache (slug → display name), refreshed every 5 minutes
let _patientNameMap: Record<string, string> = {}
let _patientNameMapExpiry = 0
const PATIENT_NAME_MAP_TTL_MS = 5 * 60 * 1000

async function getPatientNameMap(oncoteamApiUrl: string, apiKey: string): Promise<Record<string, string>> {
  if (Date.now() < _patientNameMapExpiry && Object.keys(_patientNameMap).length > 0) {
    return _patientNameMap
  }
  try {
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const data = await $fetch<{ patients: Array<{ slug: string; name?: string }> }>(
      `${oncoteamApiUrl}/api/patients`,
      { headers, signal: AbortSignal.timeout(3000) },
    )
    const map: Record<string, string> = {}
    for (const p of data.patients || []) {
      if (p.slug && p.name) map[p.slug] = p.name
    }
    _patientNameMap = map
    _patientNameMapExpiry = Date.now() + PATIENT_NAME_MAP_TTL_MS
    return map
  }
  catch {
    return _patientNameMap // return stale on error
  }
}

function mimeToExt(contentType: string): string {
  // Normalize: strip codec params (e.g. "audio/ogg; codecs=opus" → "audio/ogg")
  const mime = contentType.split(';')[0].trim()
  const map: Record<string, string> = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'application/pdf': 'pdf',
    'audio/ogg': 'ogg',
    'audio/mpeg': 'mp3',
    'audio/mp4': 'm4a',
    'audio/amr': 'amr',
  }
  return map[mime] || 'bin'
}

function isAudioMime(contentType: string): boolean {
  return contentType.startsWith('audio/')
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

  // Validate Twilio signature (try proxy URL, https variant, and configured URL)
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
  // Try configured webhook URL (exact URL Twilio signs against)
  if (!isValid && config.twilioWebhookUrl) {
    isValid = twilio.validateRequest(
      config.twilioAuthToken,
      twilioSignature,
      config.twilioWebhookUrl as string,
      body || {},
    )
  }

  // Fail-closed on signature validation failure — block unauthenticated requests
  if (!isValid) {
    // Allow bypass only if NUXT_TWILIO_WEBHOOK_URL is not set (signature URL unknown)
    if (config.twilioWebhookUrl) {
      console.error('[whatsapp-webhook] Twilio signature validation FAILED from:', from)
      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml('')  // Empty TwiML — silent reject
    }
    console.warn('[whatsapp-webhook] Twilio signature validation failed (no webhook URL configured for verification)')
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
  const roleMap = await getRoleMap()
  const allowedPhones = extractPhoneAllowlist(roleMap)

  // Fail-closed: if ROLE_MAP is empty/missing, reject all — don't route to onboarding
  if (allowedPhones.size === 0 && !isApproved(from)) {
    console.error('[whatsapp] NUXT_ROLE_MAP is empty — failing closed. No phones authorized.')
    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Syst\u00e9m je do\u010dasne nedostupn\u00fd. Sk\u00faste nesk\u00f4r.')
  }

  let isAllowed = allowedPhones.has(from) || isApproved(from)

  // If not in local cache, double-check with backend (oncofiles-persisted phones)
  if (!isAllowed) {
    const oncoteamUrl = config.oncoteamApiUrl as string
    const apiKey = (config.oncoteamApiKey || '') as string
    const backendResult = await checkApprovedWithBackend(from, oncoteamUrl, apiKey)
    if (backendResult === 'approved') {
      isAllowed = true
    }
    else if (backendResult === 'error') {
      // Fail closed: don't route to onboarding when backend is unreachable
      console.error('[whatsapp] Backend unreachable — failing closed, not routing to onboarding')
      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml('Systém je dočasne nedostupný. Skúste neskôr. / System temporarily unavailable. Try again later.')
    }
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

    // Split: audio → voice transcription pipeline, non-audio → document pipeline
    const audioAttachments = mediaAttachments.filter(m => isAudioMime(m.contentType))
    const documentAttachments = mediaAttachments.filter(m => !isAudioMime(m.contentType))

    // ── Voice note handling ──────────────────────────────────────
    if (audioAttachments.length > 0) {
      const patientId = getActivePatientForPhone(from)
      const allowedIds = getAllowedPatientIdsForPhone(from, roleMap)
      const userInfo = getUserInfoForPhone(from, roleMap)
      const patientNameMap = await getPatientNameMap(oncoteamUrl, apiKey)

      // Fire-and-forget: transcribe + route through command handler
      ;(async () => {
        const audio = audioAttachments[0] // Take first voice note only
        try {
          const arrayBuffer = await downloadTwilioMedia(
            audio.url,
            config.twilioAccountSid as string,
            config.twilioAuthToken as string,
          )

          // Size guards
          if (arrayBuffer.byteLength < 1024) {
            await sendWhatsApp({ to: from, body: 'Hlasov\u00e1 spr\u00e1va je pr\u00edli\u0161 kr\u00e1tka. \ud83c\udfa4' })
            return
          }
          if (arrayBuffer.byteLength > 10 * 1024 * 1024) {
            await sendWhatsApp({ to: from, body: 'Hlasov\u00e1 spr\u00e1va je pr\u00edli\u0161 dlh\u00e1 (max 5 min). Sk\u00faste krat\u0161iu alebo nap\u00ed\u0161te text. \ud83c\udfa4' })
            return
          }

          const base64 = Buffer.from(arrayBuffer).toString('base64')
          const transcription = await $fetch<{ text: string; duration_s?: number; cost?: number; error?: string }>(
            `${oncoteamUrl}/api/internal/whatsapp-voice`,
            {
              method: 'POST',
              body: {
                audio_base64: base64,
                content_type: audio.contentType,
                phone: from,
                patient_id: patientId,
                lang_hint: 'sk',
              },
              headers,
              signal: AbortSignal.timeout(35_000),
            },
          )

          if (transcription.error || !transcription.text?.trim()) {
            await sendWhatsApp({ to: from, body: 'Nepodarilo sa rozpozna\u0165 hlasov\u00fa spr\u00e1vu. Sk\u00faste to znova alebo nap\u00ed\u0161te text. \ud83c\udfa4\u274c' })
            return
          }

          const text = transcription.text.trim()
          const voicePrefix = `\ud83c\udfa4 \u201e${text.slice(0, 200)}\u201c\n\n`

          // Route transcribed text through normal command pipeline
          const rawResult: CommandResult = await handleWhatsAppCommand(text, oncoteamUrl, from, {
            patientId,
            allowedPatientIds: allowedIds,
            hasMultiplePatients: allowedIds.length > 1,
            patientNameMap,
            userName: userInfo.name,
            userRoles: userInfo.roles,
          })
          // #382 — append medical-info-traceability disclaimer to every
          // synchronous command reply. Claude-conversational (async)
          // replies already get the disclaimer from api_whatsapp.py.
          const voiceLang: 'sk' | 'en' = text.match(/[čďľňŕšťžáéíóúôä]/i) ? 'sk' : 'en'
          const result = appendMedicalDisclaimer(rawResult, voiceLang)

          if (result.type === 'reply') {
            await sendWhatsApp({ to: from, body: (voicePrefix + result.text).slice(0, 1600) })
          }
          else if (result.type === 'multi') {
            const segments = [...result.segments]
            segments[0] = voicePrefix + segments[0]
            for (const seg of segments) {
              await sendWhatsApp({ to: from, body: seg.slice(0, 1600) })
              await new Promise(r => setTimeout(r, 150))
            }
          }
          else if (result.type === 'async') {
            // Conversational AI — send interim ack with transcription
            const patientLabel = patientNameMap[patientId] || patientId
            await sendWhatsApp({ to: from, body: `${voicePrefix}Prem\u00fd\u0161\u013eam... (~30s) \ud83e\udd14\n\ud83d\udccb ${patientLabel}` })

            const chatResult = await $fetch<{ response: string }>(`${oncoteamUrl}/api/internal/whatsapp-chat`, {
              method: 'POST',
              body: {
                message: result.message,
                lang: result.lang,
                phone: from,
                patient_id: patientId,
                user_name: userInfo.name,
                user_roles: userInfo.roles,
              },
              headers,
              signal: AbortSignal.timeout(55_000),
            })
            await sendWhatsApp({ to: from, body: chatResult.response || 'Prep\u00e1\u010dte, nepodarilo sa spracova\u0165 spr\u00e1vu.' })
          }

          // Log with voice metadata
          $fetch(`${oncoteamUrl}/api/internal/log-whatsapp`, {
            method: 'POST',
            body: { phone: from, user_message: `[\ud83c\udfa4 voice] ${text}`, bot_response: '(async)', patient_id: patientId, user_name: userInfo.name, input_type: 'voice', duration_s: transcription.duration_s },
            headers,
          }).catch(() => {})
        }
        catch (err) {
          console.error('[whatsapp-voice] Transcription pipeline failed:', err)
          await sendWhatsApp({ to: from, body: 'Nepodarilo sa rozpozna\u0165 hlasov\u00fa spr\u00e1vu. Sk\u00faste to znova alebo nap\u00ed\u0161te text. \ud83c\udfa4\u274c' }).catch(() => {})
        }
      })()

      // Also process any non-audio attachments in parallel
      if (documentAttachments.length > 0) {
        ;(async () => {
          for (const media of documentAttachments) {
            try {
              const arrayBuffer = await downloadTwilioMedia(media.url, config.twilioAccountSid as string, config.twilioAuthToken as string)
              const base64 = Buffer.from(arrayBuffer).toString('base64')
              const filename = generateMediaFilename(media.contentType)
              await $fetch(`${oncoteamUrl}/api/internal/whatsapp-media`, { method: 'POST', body: { media_base64: base64, content_type: media.contentType, filename, phone: from, patient_id: patientId }, headers })
            }
            catch (err) { console.error('[whatsapp-media] Failed:', err) }
          }
        })()
      }

      setResponseHeader(event, 'content-type', 'text/xml')
      return twiml('Prep\u00ed\u0161em hlasov\u00fa spr\u00e1vu... \ud83c\udfa4')
    }

    // ── Document-only media (no audio) ──────────────────────────────
    // Fire-and-forget: download, upload, analyze, respond via Twilio REST
    ;(async () => {
      const results: string[] = []
      for (const media of documentAttachments) {
        try {
          const arrayBuffer = await downloadTwilioMedia(
            media.url,
            config.twilioAccountSid as string,
            config.twilioAuthToken as string,
          )
          const base64 = Buffer.from(arrayBuffer).toString('base64')
          const filename = generateMediaFilename(media.contentType)

          const result = await $fetch<{ status: string; document_id: string; summary: string; pipeline?: string }>(
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
          const summary = result.summary || 'Dokument bol nahran\u00fd.'
          const pipelineNote = result.pipeline === 'started'
            ? '\n\ud83d\udd04 Sp\u00fa\u0161\u0165am anal\u00fdzu \u2014 lab\u00e1ky a hodnoty sa extrahuj\u00fa automaticky.'
            : ''
          results.push(`\ud83d\udcc4 ${filename}: ${summary}${pipelineNote}`)
        }
        catch (err) {
          console.error('[whatsapp-media] Failed to process attachment:', err)
          results.push('Chyba pri spracovan\u00ed pr\u00edlohy.')
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
        body: { phone: from, user_message: `[media x${documentAttachments.length}] ${messageBody}`, bot_response: reply },
        headers,
      }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
    })()

    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml('Spracov\u00e1vam dokument... \ud83d\udcc4')
  }

  // Process command and respond
  const oncoteamApiUrl = config.oncoteamApiUrl as string
  const apiKey = (config.oncoteamApiKey || '') as string
  const allowedPatientIds = getAllowedPatientIdsForPhone(from, roleMap)
  const whatsappPatientId = getActivePatientForPhone(from)
  const hasMultiplePatients = allowedPatientIds.length > 1
  const userInfo = getUserInfoForPhone(from, roleMap)
  const patientNameMap = await getPatientNameMap(oncoteamApiUrl, apiKey)
  const rawCommandResult: CommandResult = await handleWhatsAppCommand(messageBody, oncoteamApiUrl, from, { patientId: whatsappPatientId, allowedPatientIds, hasMultiplePatients, patientNameMap, userName: userInfo.name, userRoles: userInfo.roles })
  // #382 — append medical-info-traceability disclaimer to every
  // synchronous command reply. Async (Claude-conversational) path keeps
  // the disclaimer it already gets from api_whatsapp.py — see
  // `appendMedicalDisclaimer` implementation which skips type='async'.
  const cmdLang: 'sk' | 'en' = messageBody.match(/[čďľňŕšťžáéíóúôä]/i) ? 'sk' : 'en'
  const result: CommandResult = appendMedicalDisclaimer(rawCommandResult, cmdLang)

  if (result.type === 'async') {
    // Conversational message — respond immediately, send Claude's answer async.
    // Claude API takes 30-60s, exceeding Twilio's 15s webhook timeout.

    // Fire-and-forget: call Claude API and send response via Twilio REST API
    ;(async () => {
      const asyncStartMs = Date.now()
      const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}

      // Step 1: Get Claude response (55s timeout — generous for autonomous agent)
      let reply: string
      try {
        console.log('[whatsapp-async] Calling Claude API for:', result.message.slice(0, 50))
        const chatResult = await $fetch<{ response: string }>(`${oncoteamApiUrl}/api/internal/whatsapp-chat`, {
          method: 'POST',
          body: {
            message: result.message,
            lang: result.lang,
            phone: from,
            patient_id: whatsappPatientId,
            user_name: userInfo.name,
            user_roles: userInfo.roles,
          },
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
          ? 'Prepáčte, nepodarilo sa spracovať správu. Skúste príkaz ako *labáky* alebo *pomoc*.'
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

      // Step 3: Log exchange with audit metadata
      $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        body: {
          phone: from,
          user_message: messageBody,
          bot_response: reply,
          patient_id: whatsappPatientId,
          user_name: userInfo.name,
          command: 'conversational',
          lang: result.lang,
          response_time_ms: Date.now() - asyncStartMs,
        },
        headers,
      }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
    })()

    // Immediate response to Twilio — acknowledge receipt
    setResponseHeader(event, 'content-type', 'text/xml')
    const patientLabel = patientNameMap[whatsappPatientId] || whatsappPatientId
    const ackMsg = result.lang === 'sk'
      ? `Premýšľam... (~30s) 🤔\n📋 ${patientLabel}`
      : `Thinking... (~30s) 🤔\n📋 ${patientLabel}`
    return twiml(ackMsg)
  }

  // Multi-segment response: first segment via TwiML, rest via Twilio REST API
  if (result.type === 'multi') {
    const segments = result.segments
    const firstReply = segments[0] || ''
    const remaining = segments.slice(1)

    if (remaining.length > 0) {
      ;(async () => {
        // Send remaining segments with 150ms delay for correct ordering
        for (const segment of remaining) {
          await new Promise(resolve => setTimeout(resolve, 150))
          const sendResult = await sendWhatsApp({ to: from, body: segment })
          if (!sendResult.ok) {
            console.error('[whatsapp-multi] Segment send failed:', sendResult.error)
          }
        }
      })()
    }

    // Log the full exchange with audit metadata
    try {
      const logHeaders: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
      $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        body: {
          phone: from,
          user_message: messageBody,
          bot_response: segments.join('\n---\n'),
          patient_id: whatsappPatientId,
          user_name: userInfo.name,
          command: 'multi',
          lang: result.lang || 'sk',
        },
        headers: logHeaders,
      }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
    }
    catch {
      // Logging failure must not block the response
    }

    setResponseHeader(event, 'content-type', 'text/xml')
    return twiml(firstReply)
  }

  // Synchronous command response
  const reply = result.text

  // Log the WhatsApp exchange to oncofiles (fire-and-forget) with audit metadata
  try {
    const logHeaders: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    $fetch(`${oncoteamApiUrl}/api/internal/log-whatsapp`, {
      method: 'POST',
      body: {
        phone: from,
        user_message: messageBody,
        bot_response: reply,
        patient_id: whatsappPatientId,
        user_name: userInfo.name,
        command: 'sync_command',
        lang: 'sk',
      },
      headers: logHeaders,
    }).catch((err: unknown) => console.warn('[whatsapp] Non-critical async failed:', (err as Error)?.message || err))
  }
  catch {
    // Logging failure must not block the response
  }

  setResponseHeader(event, 'content-type', 'text/xml')
  return twiml(reply)
})
