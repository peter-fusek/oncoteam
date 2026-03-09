const MAX_REPLY_LENGTH = 1500

const COMMAND_MAP: Record<string, string> = {
  // Slovak
  labky: 'labs',
  lieky: 'meds',
  stav: 'status',
  pomoc: 'help',
  casovka: 'timeline',
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
  if (!entries.length) return 'Zatial ziadne labky v systeme.\n\nLab data sa syncne po prvom analyze_labs cez Oncoteam.'

  // Show all entries (most recent first)
  let text = '*Labky*\n'
  for (const entry of entries.slice(0, 3)) {
    const date = entry.date || 'N/A'
    const statuses = (entry.value_statuses || {}) as Record<string, string>
    const values = (entry.values || {}) as Record<string, unknown>
    const notes = entry.notes as string | undefined

    text += `\n*${date}*\n`
    const flagged: string[] = []
    const normal: string[] = []

    for (const [key, val] of Object.entries(values)) {
      const status = statuses[key] || 'normal'
      const flag = status === 'high' ? '⬆️' : status === 'low' ? '⬇️' : ''
      const line = `${key}: ${val}${flag}`
      if (flag) flagged.push(line)
      else normal.push(line)
    }

    if (flagged.length) text += `⚠️ ${flagged.join(', ')}\n`
    if (normal.length) text += `${normal.join(' | ')}\n`
    if (notes) text += `📝 ${notes.slice(0, 120)}\n`
  }

  return truncate(text)
}

function formatMeds(data: Record<string, unknown>): string {
  // Use tracked medications first, fall back to default_medications from protocol
  const tracked = (data.medications || []) as Array<Record<string, unknown>>
  const defaults = (data.default_medications || []) as Array<Record<string, unknown>>
  const meds = tracked.length > 0 ? tracked : defaults
  const isDefault = tracked.length === 0 && defaults.length > 0

  if (!meds.length) return 'Ziadne lieky v systeme.'

  let text = `*Lieky${isDefault ? ' (protokol)' : ''}*\n\n`
  for (const med of meds) {
    const active = med.active !== false
    const icon = active ? '💊' : '⏸️'
    text += `${icon} *${med.name}* — ${med.dose || 'N/A'}\n`
    text += `   ${med.frequency || ''}`
    if (med.notes) text += ` (${String(med.notes).slice(0, 80)})`
    text += '\n'
  }

  const adherence = data.adherence as Record<string, unknown> | undefined
  if (adherence?.compliance_pct != null) {
    text += `\nCompliance: ${adherence.compliance_pct}%`
  }

  return truncate(text)
}

function formatBriefing(data: Record<string, unknown>): string {
  const briefings = (data.briefings || []) as Array<Record<string, unknown>>
  if (!briefings.length) {
    return 'Zatial ziadne briefingy.\n\nBriefingy sa generuju automaticky cez autonomous agent (daily_briefing task).'
  }

  const latest = briefings[0]
  const date = latest.date || latest.created_at || 'N/A'
  const content = String(latest.content || latest.summary || 'No content')

  return truncate(`*Briefing (${date})*\n\n${content}`)
}

function formatTimeline(data: Record<string, unknown>): string {
  const events = (data.events || []) as Array<Record<string, unknown>>
  if (!events.length) return 'Ziadne udalosti v timeline.'

  let text = `*Timeline (${events.length} udalosti)*\n`
  for (const ev of events.slice(0, 5)) {
    const type = ev.type as string || ''
    const icon = type === 'chemo' ? '💉' : type.includes('pathology') ? '🧬' : type === 'lab_result' ? '🔬' : '📅'
    text += `\n${icon} *${ev.date || 'N/A'}*\n${ev.title || 'Event'}\n`
  }

  return truncate(text)
}

function formatStatus(data: Record<string, unknown>): string {
  let text = `*Oncoteam Status*\n\n`
  text += `Server: ${data.status === 'ok' ? '✅ OK' : '❌ ' + data.status}\n`
  text += `Version: ${data.version || 'N/A'}\n`
  text += `Tools: ${data.tools_count || 'N/A'}\n`
  text += `Session: ${data.session_id || 'N/A'}\n`

  return truncate(text)
}

function helpText(): string {
  return `*Oncoteam WhatsApp*

Prikazy:
• *labky* / *labs* — Posledne labky
• *lieky* / *meds* — Lieky a compliance
• *casovka* / *timeline* — Udalosti liecby
• *briefing* — Posledny briefing
• *stav* / *status* — Stav systemu
• *pomoc* / *help* — Tento help

Posli prikaz a dostanes odpoved.`
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
    return `⚠️ Chyba: ${message}\n\nSkus znova neskor alebo posli *pomoc*.`
  }
}
