import twilio from 'twilio'

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }

  const config = useRuntimeConfig()
  const { message, recipientPhone } = await readBody(event)

  if (!message || typeof message !== 'string') {
    throw createError({ statusCode: 400, message: 'Message is required' })
  }

  const phone = recipientPhone || session.user.phone
  if (!phone) {
    throw createError({ statusCode: 400, message: 'No phone number configured' })
  }

  if (!config.twilioAccountSid || !config.twilioAuthToken || !config.twilioWhatsappFrom) {
    throw createError({ statusCode: 500, message: 'WhatsApp not configured' })
  }

  const roleName = session.user.activeRole || 'advocate'
  const userName = session.user.name || session.user.email
  const fullMessage = `📋 Oncoteam Update\nPatient: Erika | For: ${userName} (${roleName})\n---\n${message}`

  const client = twilio(config.twilioAccountSid, config.twilioAuthToken)

  const result = await client.messages.create({
    from: config.twilioWhatsappFrom,
    to: `whatsapp:${phone}`,
    body: fullMessage,
  })

  return { ok: true, sid: result.sid }
})
