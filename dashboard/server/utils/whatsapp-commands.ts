const MAX_REPLY_LENGTH = 1500

const COMMAND_MAP: Record<string, string> = {
  // Slovak
  labky: 'labs',
  lieky: 'meds',
  stav: 'status',
  pomoc: 'help',
  // English
  labs: 'labs',
  meds: 'meds',
  medications: 'meds',
  status: 'status',
  briefing: 'briefing',
  timeline: 'timeline',
  help: 'help',
}

function truncate(text: string, max: number = MAX_REPLY_LENGTH): string {
  if (text.length <= max) return text
  return text.slice(0, max - 3) + '...'
}

function formatLabs(data: Record<string, unknown>): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  if (!entries.length) return 'No lab data available.'

  const latest = entries[0]
  const date = latest.date || 'N/A'
  const statuses = (latest.value_statuses || {}) as Record<string, string>
  const values = (latest.values || {}) as Record<string, unknown>

  let text = `*Labky (${date})*\n`
  const flagged: string[] = []
  const normal: string[] = []

  for (const [key, val] of Object.entries(values)) {
    const status = statuses[key] || 'normal'
    const flag = status === 'high' ? '⬆️' : status === 'low' ? '⬇️' : ''
    const line = `${key}: ${val}${flag}`
    if (flag) flagged.push(line)
    else normal.push(line)
  }

  if (flagged.length) {
    text += `\n⚠️ *Flagged:*\n${flagged.join('\n')}\n`
  }
  if (normal.length) {
    text += `\n✅ Normal:\n${normal.join(' | ')}`
  }

  return truncate(text)
}

function formatMeds(data: Record<string, unknown>): string {
  const medications = (data.medications || []) as Array<Record<string, unknown>>
  if (!medications.length) return 'No medications tracked.'

  const active = medications.filter(m => m.status === 'active' || !m.status)
  const compliance = data.compliance_percent

  let text = `*Lieky*\n`
  for (const med of active) {
    text += `• ${med.name} — ${med.dose || ''} (${med.frequency || ''})\n`
  }
  if (compliance !== undefined) {
    text += `\nCompliance: ${compliance}%`
  }

  return truncate(text)
}

function formatBriefing(data: Record<string, unknown>): string {
  const briefings = (data.briefings || []) as Array<Record<string, unknown>>
  if (!briefings.length) return 'No briefings available.'

  const latest = briefings[0]
  const date = latest.date || latest.created_at || 'N/A'
  const content = String(latest.content || latest.summary || 'No content')

  return truncate(`*Briefing (${date})*\n\n${content}`)
}

function formatTimeline(data: Record<string, unknown>): string {
  const events = (data.events || []) as Array<Record<string, unknown>>
  if (!events.length) return 'No timeline events.'

  let text = `*Timeline (last ${Math.min(5, events.length)})*\n`
  for (const ev of events.slice(0, 5)) {
    text += `\n📅 ${ev.date || 'N/A'} — ${ev.title || ev.event_type || 'Event'}`
    if (ev.description) text += `\n   ${String(ev.description).slice(0, 100)}`
  }

  return truncate(text)
}

function formatStatus(data: Record<string, unknown>): string {
  let text = `*Oncoteam Status*\n`
  text += `Server: ${data.status || 'unknown'}\n`
  if (data.uptime) text += `Uptime: ${data.uptime}\n`
  if (data.tools_count) text += `Tools: ${data.tools_count}\n`
  if (data.next_milestone) text += `\nNext milestone: ${JSON.stringify(data.next_milestone)}`

  return truncate(text)
}

function helpText(): string {
  return `*Oncoteam WhatsApp*

Available commands:
• *labky* / *labs* — Latest lab results
• *lieky* / *meds* — Medications & compliance
• *briefing* — Latest autonomous briefing
• *timeline* — Recent treatment events
• *stav* / *status* — System status
• *pomoc* / *help* — This help message

Send any command to get started.`
}

export async function handleWhatsAppCommand(body: string, oncoteamApiUrl: string): Promise<string> {
  const input = body.trim().toLowerCase().split(/\s+/)[0] || ''
  const command = COMMAND_MAP[input]

  if (!command || command === 'help') {
    return helpText()
  }

  const apiMap: Record<string, string> = {
    labs: '/api/labs',
    meds: '/api/medications',
    briefing: '/api/briefings?limit=1',
    timeline: '/api/timeline?limit=5',
    status: '/api/status',
  }

  const endpoint = apiMap[command]
  if (!endpoint) return helpText()

  try {
    const data = await $fetch<Record<string, unknown>>(`${oncoteamApiUrl}${endpoint}`)

    switch (command) {
      case 'labs': return formatLabs(data)
      case 'meds': return formatMeds(data)
      case 'briefing': return formatBriefing(data)
      case 'timeline': return formatTimeline(data)
      case 'status': return formatStatus(data)
      default: return helpText()
    }
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    return `⚠️ Error fetching data: ${message}\n\nTry again later or send *help* for commands.`
  }
}
