import { addApprovedPhone, setPhonePatient, resolvePatientIdFromPhone } from './approved-phones'

const MAX_REPLY_LENGTH = 1500

type Lang = 'sk' | 'en'

const SLOVAK_COMMANDS = new Set(['labky', 'lieky', 'stav', 'pomoc', 'casovka', 'naklady', 'studie', 'cyklus', 'schval', 'prepni', 'pacienti'])
const ENGLISH_COMMANDS = new Set(['labs', 'meds', 'medications', 'status', 'briefing', 'timeline', 'help', 'cost', 'trials', 'cycle', 'approve', 'switch', 'patients'])

const COMMAND_MAP: Record<string, string> = {
  // Slovak
  labky: 'labs',
  lieky: 'meds',
  stav: 'status',
  pomoc: 'help',
  casovka: 'timeline',
  naklady: 'cost',
  studie: 'trials',
  cyklus: 'cycle',
  schval: 'approve',
  prepni: 'switch',
  pacienti: 'patients',
  // English
  labs: 'labs',
  meds: 'meds',
  medications: 'meds',
  status: 'status',
  briefing: 'briefing',
  timeline: 'timeline',
  help: 'help',
  cost: 'cost',
  trials: 'trials',
  cycle: 'cycle',
  approve: 'approve',
  switch: 'switch',
  patients: 'patients',
}

function detectLang(input: string): Lang {
  if (SLOVAK_COMMANDS.has(input)) return 'sk'
  if (ENGLISH_COMMANDS.has(input)) return 'en'
  return 'sk'
}

const L = (sk: string, en: string) => ({ sk, en })
const t = (msg: { sk: string; en: string }, lang: Lang) => msg[lang]

function truncate(text: string, max: number = MAX_REPLY_LENGTH): string {
  if (text.length <= max) return text
  return text.slice(0, max - 3) + '...'
}

function formatLabs(data: Record<string, unknown>, lang: Lang): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  if (!entries.length) {
    return t(L(
      'Zatial ziadne labky v systeme.\n\nLab data sa syncne po prvom analyze_labs cez Oncoteam.',
      'No lab data in the system yet.\n\nLab data will sync after the first analyze_labs via Oncoteam.',
    ), lang)
  }

  let text = t(L('*Labky*\n', '*Labs*\n'), lang)
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

function formatMeds(data: Record<string, unknown>, lang: Lang): string {
  const tracked = (data.medications || []) as Array<Record<string, unknown>>
  const defaults = (data.default_medications || []) as Array<Record<string, unknown>>
  const meds = tracked.length > 0 ? tracked : defaults
  const isDefault = tracked.length === 0 && defaults.length > 0

  if (!meds.length) return t(L('Ziadne lieky v systeme.', 'No medications in the system.'), lang)

  const header = isDefault
    ? t(L('*Lieky (protokol)*', '*Medications (protocol)*'), lang)
    : t(L('*Lieky*', '*Medications*'), lang)
  let text = `${header}\n\n`

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
    text += `\n${t(L('Adherencia', 'Compliance'), lang)}: ${adherence.compliance_pct}%`
  }

  return truncate(text)
}

function formatBriefing(data: Record<string, unknown>, lang: Lang): string {
  const briefings = (data.briefings || []) as Array<Record<string, unknown>>
  if (!briefings.length) {
    return t(L(
      'Zatial ziadne briefingy.\n\nBriefingy sa generuju automaticky cez autonomous agent (daily_briefing task).',
      'No briefings yet.\n\nBriefings are generated automatically by the autonomous agent (daily_briefing task).',
    ), lang)
  }

  const latest = briefings[0]
  const date = latest.date || latest.created_at || 'N/A'
  const content = String(latest.content || latest.summary || t(L('Bez obsahu', 'No content'), lang))

  return truncate(`*Briefing (${date})*\n\n${content}`)
}

function formatTimeline(data: Record<string, unknown>, lang: Lang): string {
  const events = (data.events || []) as Array<Record<string, unknown>>
  if (!events.length) return t(L('Ziadne udalosti v timeline.', 'No events in the timeline.'), lang)

  const header = t(L(`*Casova os (${events.length} udalosti)*`, `*Timeline (${events.length} events)*`), lang)
  let text = `${header}\n`
  for (const ev of events.slice(0, 5)) {
    const type = ev.type as string || ''
    const icon = type === 'chemo' || type === 'chemo_cycle' ? '💉' : type.includes('pathology') ? '🧬' : type === 'lab_work' || type === 'lab_result' ? '🔬' : '📅'
    text += `\n${icon} *${ev.date || 'N/A'}*\n${ev.title || t(L('Udalost', 'Event'), lang)}\n`
  }

  return truncate(text)
}

function formatStatus(data: Record<string, unknown>, lang: Lang): string {
  let text = `*Oncoteam Status*\n\n`
  text += `${t(L('Server', 'Server'), lang)}: ${data.status === 'ok' ? '✅ OK' : '❌ ' + data.status}\n`
  text += `${t(L('Verzia', 'Version'), lang)}: ${data.version || 'N/A'}\n`
  text += `${t(L('Nastroje', 'Tools'), lang)}: ${data.tools_count || 'N/A'}\n`
  text += `${t(L('Sedenie', 'Session'), lang)}: ${data.session_id || 'N/A'}\n`

  return truncate(text)
}

function formatCost(data: Record<string, unknown>, lang: Lang): string {
  const today = data.today_spend as number ?? 0
  const cap = data.daily_cap as number ?? 0
  const mtd = data.mtd_spend as number ?? 0
  const remaining = data.remaining_credit as number ?? 0
  const daysLeft = data.days_remaining as number ?? 0
  const alert = data.budget_alert as boolean ?? false

  const header = t(L('*Náklady autonómneho agenta*', '*Autonomous Agent Cost*'), lang)
  let text = `${header}\n\n`
  text += `${t(L('Dnes', 'Today'), lang)}: $${today.toFixed(2)} / $${cap.toFixed(2)}\n`
  text += `${t(L('Mesiac (MTD)', 'Month (MTD)'), lang)}: $${mtd.toFixed(2)}\n`
  text += `${t(L('Zostatok', 'Remaining'), lang)}: $${remaining.toFixed(2)}\n`
  text += `${t(L('Odhad dní', 'Est. days left'), lang)}: ${daysLeft.toFixed(0)}\n`
  if (alert) text += `\n⚠️ ${t(L('Nízky zostatok!', 'Low balance!'), lang)}`

  return truncate(text)
}

function formatTrials(data: Record<string, unknown>, lang: Lang): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  const high = entries.filter(e => e.relevance_tier === 'high')
  if (!entries.length) return t(L('Ziadne studie v systeme.', 'No trials in the system.'), lang)

  const header = t(
    L(`*Klinické štúdie* (${high.length} vysoko relevantných z ${entries.length})`,
      `*Clinical Trials* (${high.length} high relevance of ${entries.length})`),
    lang,
  )
  let text = `${header}\n`
  for (const e of high.slice(0, 5)) {
    const src = e.source === 'clinicaltrials' ? '🧪' : '📄'
    text += `\n${src} *${e.external_id || 'N/A'}*\n${String(e.title || '').slice(0, 100)}\n`
  }
  text += `\n${t(L('Viac na dashboarde: /research', 'More on dashboard: /research'), lang)}`
  return truncate(text)
}

function formatCycle(data: Record<string, unknown>, lang: Lang): string {
  const protocol = data as Record<string, unknown>
  const cycle = protocol.current_cycle || 3
  const regimen = protocol.regimen || 'mFOLFOX6'

  let text = t(
    L(`*Cyklus ${cycle}* — ${regimen}\n`, `*Cycle ${cycle}* — ${regimen}\n`),
    lang,
  )

  const labs = protocol.last_lab_values as Record<string, Record<string, unknown>> | undefined
  if (labs) {
    text += `\n${t(L('Posledné labky:', 'Latest labs:'), lang)}\n`
    for (const [param, info] of Object.entries(labs)) {
      if (info?.value != null) {
        const status = info.status === 'critical' ? '🔴' : info.status === 'warning' ? '🟡' : '🟢'
        text += `${status} ${param}: ${info.value}\n`
      }
    }
  }

  return truncate(text)
}

async function handleApproveCommand(
  body: string,
  oncoteamApiUrl: string,
  lang: Lang,
  fromPhone?: string,
): Promise<CommandResult> {
  // Admin check: only phones in the role map can approve
  const config = useRuntimeConfig()
  const adminPhones = extractAdminPhones(config.roleMap)
  const callerPhone = fromPhone ? fromPhone.replace(/[\s\-()]/g, '') : ''

  if (!callerPhone || !adminPhones.has(callerPhone)) {
    return {
      type: 'reply',
      text: t(L(
        'Tento prikaz je len pre administratorov.',
        'This command is for admins only.',
      ), lang),
    }
  }

  // Extract phone number from command: "approve +421900111222" or "schval +421900111222"
  const parts = body.trim().split(/\s+/)
  const rawPhone = parts.slice(1).join('')
  if (!rawPhone) {
    return {
      type: 'reply',
      text: t(L(
        'Pouzitie: *schval +421XXXXXXXXX*',
        'Usage: *approve +421XXXXXXXXX*',
      ), lang),
    }
  }

  const phoneToApprove = normalizeApprovalPhone(rawPhone)
  if (phoneToApprove.length < 8) {
    return {
      type: 'reply',
      text: t(L(
        'Neplatne telefonne cislo. Pouzitie: *schval +421XXXXXXXXX*',
        'Invalid phone number. Usage: *approve +421XXXXXXXXX*',
      ), lang),
    }
  }

  try {
    const apiKey = (config.oncoteamApiKey || '') as string
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}

    await $fetch(`${oncoteamApiUrl}/api/internal/approve-user`, {
      method: 'POST',
      body: { phone: phoneToApprove },
      headers,
    })

    // Also add to local runtime set so webhook picks it up immediately
    addApprovedPhone(phoneToApprove)

    return {
      type: 'reply',
      text: t(L(
        `Telefon ${phoneToApprove} schvaleny. Pouzivatel ma teraz pristup.`,
        `Phone ${phoneToApprove} approved. User now has access.`,
      ), lang),
    }
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    return {
      type: 'reply',
      text: t(L(
        `Chyba pri schvalovani: ${message}`,
        `Approval error: ${message}`,
      ), lang),
    }
  }
}

function helpText(lang: Lang): string {
  if (lang === 'en') {
    return `*Oncoteam WhatsApp*

Commands:
• *labs* / *labky* — Latest lab results
• *meds* / *lieky* — Medications and compliance
• *cycle* / *cyklus* — Current cycle status
• *trials* / *studie* — Clinical trial matches
• *timeline* / *casovka* — Treatment events
• *briefing* — Latest briefing
• *cost* / *naklady* — AI agent cost & budget
• *patients* / *pacienti* — List patients
• *switch <slug>* / *prepni <meno>* — Switch patient
• *status* / *stav* — System status
• *help* / *pomoc* — This help

Send a command or a question.`
  }

  return `*Oncoteam WhatsApp*

Prikazy:
• *labky* / *labs* — Posledne labky
• *lieky* / *meds* — Lieky a compliance
• *cyklus* / *cycle* — Stav aktualneho cyklu
• *studie* / *trials* — Klinicke studie
• *casovka* / *timeline* — Udalosti liecby
• *briefing* — Posledny briefing
• *naklady* / *cost* — Naklady a rozpocet AI agenta
• *pacienti* / *patients* — Zoznam pacientov
• *prepni <meno>* / *switch <slug>* — Prepni pacienta
• *stav* / *status* — Stav systemu
• *pomoc* / *help* — Tento help

Posli prikaz alebo otazku.`
}

export type CommandResult =
  | { type: 'reply'; text: string }
  | { type: 'async'; lang: Lang; message: string }

function extractAdminPhones(roleMapRaw: string | Record<string, { phone?: string; roles?: string[] }>): Set<string> {
  try {
    const roleMap = typeof roleMapRaw === 'string' ? JSON.parse(roleMapRaw || '{}') : roleMapRaw || {}
    const phones = new Set<string>()
    for (const [key, config] of Object.entries(roleMap) as Array<[string, { phone?: string; roles?: string[] }]>) {
      // Only admin/advocate roles can approve — not patients or doctors
      const isAdmin = key.startsWith('admin') || key.startsWith('advocate')
        || (config.roles && (config.roles.includes('admin') || config.roles.includes('advocate')))
      if (isAdmin && config.phone) phones.add(config.phone.replace(/[\s\-()]/g, ''))
    }
    return phones
  }
  catch {
    return new Set()
  }
}

function normalizeApprovalPhone(raw: string): string {
  // Strip spaces, dashes, parens; ensure + prefix
  let phone = raw.replace(/[\s\-()]/g, '')
  if (phone && !phone.startsWith('+')) phone = '+' + phone
  return phone
}

function handleSwitchCommand(
  body: string,
  lang: Lang,
  fromPhone?: string,
): CommandResult {
  const parts = body.trim().split(/\s+/)
  const slug = parts[1]?.toLowerCase()

  if (!slug) {
    return {
      type: 'reply',
      text: t(L(
        'Pouzitie: *prepni erika* alebo *prepni e5g*\n\nPouzi *pacienti* pre zoznam.',
        'Usage: *switch erika* or *switch e5g*\n\nUse *patients* to list available.',
      ), lang),
    }
  }

  if (fromPhone) {
    setPhonePatient(fromPhone.replace(/[\s\-()]/g, ''), slug)
  }

  return {
    type: 'reply',
    text: t(L(
      `Prepnute na pacienta: *${slug}*\n\nVsetky prikazy teraz zobrazuju data pre ${slug}.`,
      `Switched to patient: *${slug}*\n\nAll commands now show data for ${slug}.`,
    ), lang),
  }
}

async function handlePatientsCommand(
  oncoteamApiUrl: string,
  lang: Lang,
  fromPhone?: string,
  currentPatientId?: string,
): Promise<CommandResult> {
  try {
    const config = useRuntimeConfig()
    const apiKey = config.oncoteamApiKey || ''
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const data = await $fetch<{ patients: Array<{ slug: string; name?: string; doc_count?: number; patient_type?: string; is_current?: boolean }> }>(
      `${oncoteamApiUrl}/api/patients`,
      { headers },
    )

    const patients = data.patients || []
    if (!patients.length) {
      return { type: 'reply', text: t(L('Ziadni pacienti.', 'No patients found.'), lang) }
    }

    const current = currentPatientId || resolvePatientIdFromPhone(fromPhone?.replace(/[\s\-()]/g, '') || '')
    const header = t(L('*Pacienti*\n', '*Patients*\n'), lang)
    let text = header
    for (const p of patients) {
      const active = p.slug === current || p.is_current ? ' ← ' + t(L('aktívny', 'active'), lang) : ''
      const docs = p.doc_count != null ? ` (${p.doc_count} docs)` : ''
      text += `\n👤 *${p.slug}*${p.name ? ` — ${p.name}` : ''}${docs}${active}`
    }
    text += `\n\n${t(L('Pouzi *prepni <meno>* na zmenu.', 'Use *switch <slug>* to change.'), lang)}`
    return { type: 'reply', text: truncate(text) }
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    return {
      type: 'reply',
      text: t(L(`Chyba: ${message}`, `Error: ${message}`), lang),
    }
  }
}

export async function handleWhatsAppCommand(
  body: string,
  oncoteamApiUrl: string,
  fromPhone?: string,
  options?: { patientId?: string },
): Promise<CommandResult> {
  const input = body.trim().toLowerCase().split(/\s+/)[0] || ''
  const lang = detectLang(input)
  const command = COMMAND_MAP[input]

  if (command === 'help') {
    return { type: 'reply', text: helpText(lang) }
  }

  // Admin-only: approve command
  if (command === 'approve') {
    return handleApproveCommand(body, oncoteamApiUrl, lang, fromPhone)
  }

  // Patient switching: "prepni erika" / "switch e5g"
  if (command === 'switch') {
    return handleSwitchCommand(body, lang, fromPhone)
  }

  // List patients: "pacienti" / "patients"
  if (command === 'patients') {
    return handlePatientsCommand(oncoteamApiUrl, lang, fromPhone, options?.patientId)
  }

  // Conversational fallback — handled async (Claude API takes 30-60s,
  // exceeds Twilio's 15s webhook timeout). Caller sends immediate TwiML
  // ack, then sends Claude's response via Twilio REST API.
  if (!command) {
    return { type: 'async', lang, message: body }
  }

  const apiMap: Record<string, string> = {
    labs: '/api/labs',
    meds: '/api/medications',
    briefing: '/api/briefings?limit=1',
    timeline: '/api/timeline?limit=5',
    status: '/api/status',
    cost: '/api/autonomous/cost',
    trials: '/api/research?sort=relevance&per_page=20',
    cycle: '/api/protocol',
  }

  const endpoint = apiMap[command]
  if (!endpoint) return { type: 'reply', text: helpText(lang) }

  try {
    const sep = endpoint.includes('?') ? '&' : '?'
    const config = useRuntimeConfig()
    const apiKey = config.oncoteamApiKey || ''
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    // Include patient_id in API calls for multi-patient support
    const patientId = options?.patientId || 'erika'
    const data = await $fetch<Record<string, unknown>>(`${oncoteamApiUrl}${endpoint}${sep}lang=${lang}&patient_id=${patientId}`, { headers })

    let text: string
    switch (command) {
      case 'labs': text = formatLabs(data, lang); break
      case 'meds': text = formatMeds(data, lang); break
      case 'briefing': text = formatBriefing(data, lang); break
      case 'timeline': text = formatTimeline(data, lang); break
      case 'status': text = formatStatus(data, lang); break
      case 'cost': text = formatCost(data, lang); break
      case 'trials': text = formatTrials(data, lang); break
      case 'cycle': text = formatCycle(data, lang); break
      default: text = helpText(lang)
    }
    return { type: 'reply', text }
  }
  catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    return {
      type: 'reply',
      text: t(L(
        `⚠️ Chyba: ${message}\n\nSkus znova neskor alebo posli *pomoc*.`,
        `⚠️ Error: ${message}\n\nTry again later or send *help*.`,
      ), lang),
    }
  }
}
