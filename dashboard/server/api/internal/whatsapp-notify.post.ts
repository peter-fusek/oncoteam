import { broadcastWhatsApp, type BroadcastOptions } from '../../utils/twilio-send'

/**
 * Internal WhatsApp notify endpoint for server-to-server calls.
 * Uses DASHBOARD_API_KEY auth instead of session auth.
 *
 * Routing via `recipient`:
 *   - 'caregiver' / 'advocate' / 'admin' / 'physician' — include that role,
 *     exclude 'patient'.
 *   - 'patient' — target only role_map entries with role:patient.
 *   - undefined — broadcast to all roles EXCEPT 'patient' (safe default).
 *
 * The patient must never receive infra/operational alerts unless the caller
 * explicitly opts in (#420 — circuit-breaker alerts were reaching Erika).
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
  const recipient = (body.recipient as string | undefined)?.trim().toLowerCase()

  const options: BroadcastOptions = {}
  if (recipient === 'patient') {
    options.includeRoles = ['patient']
    options.excludeRoles = []
  }
  else if (recipient) {
    options.includeRoles = [recipient]
    options.excludeRoles = ['patient']
  }
  // else: safe default — broadcast to all non-patient roles.

  const results = await broadcastWhatsApp(sanitized, templateKey, templateVars, options)

  if (results.length === 0) {
    return { ok: false, error: 'No matching phones for recipient filter', recipient: recipient ?? 'non-patient' }
  }

  return { ok: true, sent: results.length, recipient: recipient ?? 'non-patient', results }
})
