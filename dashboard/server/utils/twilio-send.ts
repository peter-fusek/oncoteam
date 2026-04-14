import twilio from 'twilio'
import { getRoleMapSync } from './access-rights'

/**
 * Shared WhatsApp message sender with template + session window support.
 *
 * WhatsApp Business API rules:
 * - Within 24h of user's last message: free-form text allowed
 * - Outside 24h window: must use pre-approved message template
 *
 * Template SIDs are configured via NUXT_WHATSAPP_TEMPLATES env var (JSON).
 */

export interface SendWhatsAppOptions {
  /** Recipient phone number (E.164 format, e.g. +421900123456) */
  to: string
  /** Message body (used for free-form within session window) */
  body: string
  /** Template key (e.g. 'lab_alert', 'welcome') — used outside 24h window */
  templateKey?: string
  /** Template variables (substituted into template placeholders) */
  templateVars?: Record<string, string>
  /** Status callback URL override */
  statusCallback?: string
}

export interface SendResult {
  ok: boolean
  sid?: string
  error?: string
  usedTemplate?: boolean
}

// Track last inbound message time per phone for session window detection
const lastInboundMap = new Map<string, number>()
const SESSION_WINDOW_MS = 24 * 60 * 60 * 1000 // 24 hours

/**
 * Record an inbound message from a phone number.
 * Call this from the webhook handler when receiving a message.
 */
export function recordInbound(phone: string): void {
  lastInboundMap.set(phone, Date.now())
}

/**
 * Check if we're within the 24h session window for a phone.
 */
export function isInSessionWindow(phone: string): boolean {
  const lastInbound = lastInboundMap.get(phone)
  if (!lastInbound) return false
  return Date.now() - lastInbound < SESSION_WINDOW_MS
}

/**
 * Parse template configuration from env var.
 * Format: JSON object mapping template keys to Twilio Content SIDs.
 * Example: {"lab_alert": "HXxxxxxxxxx", "welcome": "HXyyyyyyyyy"}
 */
function getTemplateSids(): Record<string, string> {
  try {
    const raw = process.env.NUXT_WHATSAPP_TEMPLATES || '{}'
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/**
 * Send a WhatsApp message via Twilio.
 *
 * Automatically selects between free-form text (within 24h window)
 * and template-based message (outside window).
 */
export async function sendWhatsApp(options: SendWhatsAppOptions): Promise<SendResult> {
  const config = useRuntimeConfig()

  if (!config.twilioAccountSid || !config.twilioAuthToken || !config.twilioWhatsappFrom) {
    return { ok: false, error: 'WhatsApp not configured' }
  }

  const client = twilio(config.twilioAccountSid, config.twilioAuthToken)
  const fromNumber = String(config.twilioWhatsappFrom).startsWith('whatsapp:')
    ? config.twilioWhatsappFrom
    : `whatsapp:${config.twilioWhatsappFrom}`
  const toNumber = options.to.startsWith('whatsapp:')
    ? options.to
    : `whatsapp:${options.to}`

  const inSession = isInSessionWindow(options.to.replace('whatsapp:', ''))
  const templates = getTemplateSids()
  const templateSid = options.templateKey ? templates[options.templateKey] : undefined

  try {
    // If outside session window and we have a template, use it
    if (!inSession && templateSid) {
      const createParams: Record<string, unknown> = {
        from: fromNumber,
        to: toNumber,
        contentSid: templateSid,
      }
      if (options.templateVars) {
        createParams.contentVariables = JSON.stringify(options.templateVars)
      }
      if (options.statusCallback) {
        createParams.statusCallback = options.statusCallback
      }
      const result = await client.messages.create(createParams as Parameters<typeof client.messages.create>[0])
      return { ok: true, sid: result.sid, usedTemplate: true }
    }

    // Within session window or no template available — send free-form
    const createParams: Record<string, unknown> = {
      from: fromNumber,
      to: toNumber,
      body: options.body.slice(0, 1600), // WhatsApp limit
    }
    if (options.statusCallback) {
      createParams.statusCallback = options.statusCallback
    }
    const result = await client.messages.create(createParams as Parameters<typeof client.messages.create>[0])
    return { ok: true, sid: result.sid, usedTemplate: false }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    console.error('[twilio-send] Failed to send WhatsApp:', message)
    return { ok: false, error: message }
  }
}

/**
 * Send a WhatsApp message to all phones in NUXT_ROLE_MAP.
 */
export async function broadcastWhatsApp(
  body: string,
  templateKey?: string,
  templateVars?: Record<string, string>,
): Promise<SendResult[]> {
  const roleMap = getRoleMapSync()

  const phones = new Set<string>()
  for (const entry of Object.values(roleMap)) {
    if (entry.phone) phones.add(entry.phone)
  }

  const results: SendResult[] = []
  for (const phone of phones) {
    const result = await sendWhatsApp({ to: phone, body, templateKey, templateVars })
    results.push(result)
  }
  return results
}
