import twilio from 'twilio'

/**
 * POST /api/webhook/whatsapp-status
 *
 * Twilio message status callback webhook.
 * Receives delivery status updates for outbound WhatsApp messages:
 * queued → sent → delivered → read (or failed/undelivered).
 *
 * Configure in Twilio console:
 *   Messaging → WhatsApp Senders → Status Callback URL
 *   → https://dashboard.oncoteam.cloud/api/webhook/whatsapp-status
 */

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()

  if (!config.twilioAccountSid || !config.twilioAuthToken) {
    return { ok: false, error: 'WhatsApp not configured' }
  }

  const body = await readBody(event)
  const twilioSignature = getRequestHeader(event, 'x-twilio-signature') || ''

  // Validate Twilio signature
  const requestUrl = getRequestURL(event).toString()
  let isValid = twilio.validateRequest(
    config.twilioAuthToken,
    twilioSignature,
    requestUrl,
    body || {},
  )

  // Retry with proxy URL pattern (Railway proxy may alter URL)
  if (!isValid && config.public?.appUrl) {
    const proxyUrl = `${config.public.appUrl}/api/webhook/whatsapp-status`
    isValid = twilio.validateRequest(
      config.twilioAuthToken,
      twilioSignature,
      proxyUrl,
      body || {},
    )
  }

  if (!isValid) {
    console.warn('[whatsapp-status] Invalid Twilio signature — rejecting')
    setResponseStatus(event, 403)
    return { ok: false, error: 'Invalid signature' }
  }

  // Extract status fields from Twilio callback
  const messageSid = String(body?.MessageSid || '')
  const messageStatus = String(body?.MessageStatus || '')
  const to = String(body?.To || '').replace('whatsapp:', '')
  const errorCode = body?.ErrorCode ? String(body.ErrorCode) : undefined
  const errorMessage = body?.ErrorMessage ? String(body.ErrorMessage) : undefined

  // Log status update
  const logEntry: Record<string, string | undefined> = {
    messageSid,
    status: messageStatus,
    to,
  }
  if (errorCode) {
    logEntry.errorCode = errorCode
    logEntry.errorMessage = errorMessage
  }

  // Log failures at warn level, others at info
  if (messageStatus === 'failed' || messageStatus === 'undelivered') {
    console.warn('[whatsapp-status]', JSON.stringify(logEntry))
  } else {
    console.info('[whatsapp-status]', JSON.stringify(logEntry))
  }

  // Forward to backend for persistence (fire-and-forget)
  if (config.oncoteamApiUrl && config.oncoteamApiKey) {
    try {
      const apiUrl = config.oncoteamApiUrl.replace(/\/+$/, '')
      $fetch(`${apiUrl}/api/internal/log-whatsapp`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${config.oncoteamApiKey}`,
          'Content-Type': 'application/json',
        },
        body: {
          phone: to,
          user_message: `[status:${messageStatus}]`,
          bot_response: errorMessage || messageSid,
          tags: `sys:whatsapp,sys:status_callback,status:${messageStatus}`,
        },
        timeout: 5000,
      }).catch((err: Error) => {
        console.warn('[whatsapp-status] Failed to log to backend:', err.message)
      })
    } catch {
      // Fire-and-forget — don't block Twilio response
    }
  }

  // Twilio expects 200 OK
  return { ok: true }
})
