import { addApprovedPhone } from './approved-phones'
import { getActivePatient, setActivePatient } from './whatsapp-session'

const MAX_REPLY_LENGTH = 1500
const MAX_SEGMENTS = 3

type Lang = 'sk' | 'en'

const SLOVAK_COMMANDS = new Set(['labky', 'lieky', 'stav', 'pomoc', 'casovka', 'naklady', 'studie', 'cyklus', 'schval', 'prepni', 'pacienti', 'predcyklus', 'rodina', 'otazky', 'toxicita', 'vaha', 'davka'])
const ENGLISH_COMMANDS = new Set(['labs', 'meds', 'medications', 'status', 'briefing', 'timeline', 'help', 'cost', 'trials', 'cycle', 'approve', 'switch', 'patients', 'precycle', 'family', 'questions', 'toxicity', 'weight', 'dose'])

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
  predcyklus: 'precycle',
  rodina: 'family',
  otazky: 'questions',
  toxicita: 'toxicity',
  vaha: 'weight',
  davka: 'dose',
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
  precycle: 'precycle',
  family: 'family',
  questions: 'questions',
  toxicity: 'toxicity',
  weight: 'weight',
  dose: 'dose',
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

/** Split text into WhatsApp-sized segments on paragraph boundaries. */
function splitMessage(text: string, max: number = MAX_REPLY_LENGTH): string[] {
  if (text.length <= max) return [text]
  const segments: string[] = []
  let remaining = text
  while (remaining.length > 0 && segments.length < MAX_SEGMENTS) {
    if (remaining.length <= max) {
      segments.push(remaining)
      break
    }
    // Find last \n\n within limit
    const chunk = remaining.slice(0, max)
    let splitAt = chunk.lastIndexOf('\n\n')
    if (splitAt < max * 0.3) {
      // Fallback: split at last newline
      splitAt = chunk.lastIndexOf('\n')
    }
    if (splitAt < max * 0.2) {
      // Hard cut at limit
      splitAt = max - 3
      segments.push(remaining.slice(0, splitAt) + '...')
      remaining = remaining.slice(splitAt)
    }
    else {
      segments.push(remaining.slice(0, splitAt).trimEnd())
      remaining = remaining.slice(splitAt).trimStart()
    }
  }
  if (remaining.length > 0 && segments.length >= MAX_SEGMENTS) {
    // Truncate last segment if we hit the cap
    const last = segments[segments.length - 1]!
    if (last.length > max) {
      segments[segments.length - 1] = truncate(last, max)
    }
  }
  return segments
}

/** Parse "labky cea" → { command: "labky", subarg: "cea" } */
function parseSubCommand(body: string): { commandWord: string; subarg: string } {
  const parts = body.trim().toLowerCase().split(/\s+/)
  return { commandWord: parts[0] || '', subarg: parts[1] || '' }
}

// Sub-command aliases for labs filtering
const LAB_TUMOR_MARKERS = new Set(['CEA', 'CA_19_9'])
const LAB_HEMATOLOGY = new Set(['ANC', 'PLT', 'hemoglobin', 'WBC', 'ABS_LYMPH'])
const LAB_SUB_ALIASES: Record<string, 'tumor' | 'blood' | 'liver'> = {
  cea: 'tumor', markery: 'tumor', markers: 'tumor', tumor: 'tumor',
  krv: 'blood', blood: 'blood', hema: 'blood',
  pecen: 'liver', liver: 'liver',
}
const LAB_LIVER = new Set(['ALT', 'AST', 'bilirubin'])

// Unit map for lab parameters (matches clinical_protocol.py LAB_REFERENCE_RANGES)
const LAB_UNITS: Record<string, string> = {
  ANC: '/µL', PLT: '/µL', hemoglobin: 'g/dL', creatinine: 'mg/dL',
  ALT: 'U/L', AST: 'U/L', bilirubin: 'mg/dL', CEA: 'ng/mL',
  CA_19_9: 'U/mL', WBC: '×10³/µL', ABS_LYMPH: '/µL', SII: '', NE_LY_RATIO: '',
}

function formatLabs(data: Record<string, unknown>, lang: Lang, subarg: string = ''): string[] {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  if (!entries.length) {
    return [t(L(
      'Zatial ziadne labky v systeme.\n\nLab data sa syncne po prvom analyze_labs cez Oncoteam.',
      'No lab data in the system yet.\n\nLab data will sync after the first analyze_labs via Oncoteam.',
    ), lang)]
  }

  const refs = (data.reference_ranges || {}) as Record<string, { min?: number; max?: number; unit?: string }>

  // Sub-command filtering
  const filter = LAB_SUB_ALIASES[subarg]
  const filterSet = filter === 'tumor' ? LAB_TUMOR_MARKERS
    : filter === 'blood' ? LAB_HEMATOLOGY
      : filter === 'liver' ? LAB_LIVER
        : null

  // Pagination: "labky 2" → page 2 (entries 3-5)
  const page = /^\d+$/.test(subarg) ? parseInt(subarg, 10) : 1
  const perPage = 3
  const startIdx = (page - 1) * perPage
  const pageEntries = entries.slice(startIdx, startIdx + perPage)
  if (!pageEntries.length) {
    return [t(L(
      `Žiadne ďalšie labky (strana ${page}).`,
      `No more lab data (page ${page}).`,
    ), lang)]
  }

  const filterLabel = filter
    ? ` — ${filter === 'tumor' ? t(L('markery', 'markers'), lang) : filter === 'blood' ? t(L('krvný obraz', 'hematology'), lang) : t(L('pečeň', 'liver'), lang)}`
    : ''
  const pageLabel = page > 1 ? ` (${page}/${Math.ceil(entries.length / perPage)})` : ''

  let text = t(L(`*Labky${filterLabel}*${pageLabel}\n`, `*Labs${filterLabel}*${pageLabel}\n`), lang)
  for (const entry of pageEntries) {
    const date = entry.date || 'N/A'
    const statuses = (entry.value_statuses || {}) as Record<string, string>
    const values = (entry.values || {}) as Record<string, unknown>
    const healthDirs = (entry.health_directions || {}) as Record<string, string>
    const notes = entry.notes as string | undefined

    text += `\n*${date}*\n`

    for (const [key, val] of Object.entries(values)) {
      // Apply filter if set
      if (filterSet && !filterSet.has(key)) continue

      const status = statuses[key] || 'normal'
      const unit = refs[key]?.unit || LAB_UNITS[key] || ''
      const unitStr = unit ? ` ${unit}` : ''

      // Trend arrow from health_directions
      const hDir = healthDirs[key]
      const trend = hDir === 'improving' ? ' ↓' : hDir === 'worsening' ? ' ↑' : hDir === 'stable' ? ' →' : ''
      const trendLabel = hDir === 'improving'
        ? t(L(' lepšie', ' improving'), lang)
        : hDir === 'worsening'
          ? t(L(' horšie', ' worsening'), lang)
          : ''

      if (status === 'high' || status === 'low') {
        const icon = status === 'high' ? '⬆️' : '⬇️'
        const ref = refs[key]
        const threshold = ref
          ? status === 'low' ? ` (min: ${ref.min})` : ` (max: ${ref.max})`
          : ''
        text += `${icon} ${key}: ${val}${unitStr}${threshold}${trend}${trendLabel}\n`
      }
      else {
        text += `✓ ${key}: ${val}${unitStr}${trend}${trendLabel}\n`
      }
    }
    if (notes && !filterSet) text += `📝 ${notes.slice(0, 120)}\n`
  }

  return splitMessage(text)
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

  const latest = briefings[0]!
  const date = latest.date || latest.created_at || 'N/A'
  const content = String(latest.content || latest.summary || t(L('Bez obsahu', 'No content'), lang))

  return truncate(`*Briefing (${date})*\n\n${content}`)
}

function formatTimeline(data: Record<string, unknown>, lang: Lang, subarg: string = ''): string {
  let events = (data.events || []) as Array<Record<string, unknown>>
  if (!events.length) return t(L('Ziadne udalosti v timeline.', 'No events in the timeline.'), lang)

  // Sub-command filtering
  if (subarg === 'chemo' || subarg === 'chemoterapia') {
    events = events.filter(e => {
      const type = e.type as string || ''
      return type === 'chemo' || type === 'chemo_cycle' || type === 'chemotherapy'
    })
  }
  else if (subarg === 'lab' || subarg === 'labky') {
    events = events.filter(e => {
      const type = e.type as string || ''
      return type === 'lab_work' || type === 'lab_result'
    })
  }

  if (!events.length) return t(L('Ziadne udalosti pre tento filter.', 'No events for this filter.'), lang)

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

function formatTrials(data: Record<string, unknown>, lang: Lang, subarg: string = ''): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  const high = entries.filter(e => e.relevance_tier === 'high')
  if (!entries.length) return t(L('Ziadne studie v systeme.', 'No trials in the system.'), lang)

  // Sub-command: "studie vysoke" / "trials high" — show only high relevance
  const showAll = subarg === 'vsetky' || subarg === 'all'
  const showEntries = showAll ? entries.slice(0, 10) : high.slice(0, 5)

  const header = t(
    L(`*Klinické štúdie* (${high.length} vysoko relevantných z ${entries.length})`,
      `*Clinical Trials* (${high.length} high relevance of ${entries.length})`),
    lang,
  )
  let text = `${header}\n`
  for (const e of showEntries) {
    const src = e.source === 'clinicaltrials' ? '🧪' : '📄'
    const tier = showAll ? ` [${e.relevance_tier}]` : ''
    text += `\n${src} *${e.external_id || 'N/A'}*${tier}\n${String(e.title || '').slice(0, 100)}\n`
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

function formatPrecycle(data: Record<string, unknown>, lang: Lang): string {
  const cycle = data.current_cycle || data.cycle || '?'
  const regimen = data.regimen || 'mFOLFOX6'
  const labs = data.last_lab_values as Record<string, Record<string, unknown>> | undefined

  let text = t(
    L(`*Pred-cyklus ${cycle} kontrola* — ${regimen}\n`, `*Pre-cycle ${cycle} check* — ${regimen}\n`),
    lang,
  )

  if (!labs || !Object.keys(labs).length) {
    text += `\n${t(L('Ziadne labky k dispozicii.', 'No lab data available.'), lang)}`
    return truncate(text)
  }

  // Safety parameters in clinical priority order
  const safetyParams = ['ANC', 'PLT', 'HGB', 'creatinine', 'bilirubin', 'ALT', 'AST', 'WBC']
  let allSafe = true

  for (const param of safetyParams) {
    const info = labs[param]
    if (!info?.value) continue
    const status = info.status as string
    const icon = status === 'critical' ? '🔴' : status === 'warning' ? '🟡' : '🟢'
    if (status !== 'safe') allSafe = false
    const label = t(L(
      param === 'ANC' ? 'Neutrofily (ANC)' : param === 'PLT' ? 'Trombocyty' : param === 'HGB' ? 'Hemoglobin' : param === 'creatinine' ? 'Kreatinin' : param === 'bilirubin' ? 'Bilirubin' : param,
      param === 'ANC' ? 'Neutrophils (ANC)' : param === 'PLT' ? 'Platelets' : param === 'HGB' ? 'Hemoglobin' : param === 'creatinine' ? 'Creatinine' : param === 'bilirubin' ? 'Bilirubin' : param,
    ), lang)
    text += `${icon} ${label}: ${info.value}\n`
  }

  const sampleDate = Object.values(labs).find(l => l?.sample_date)?.sample_date
  if (sampleDate) {
    text += `\n📅 ${t(L('Dátum odberu', 'Sample date'), lang)}: ${sampleDate}`
  }

  text += '\n\n'
  if (allSafe) {
    text += t(L('✅ Všetky parametre bezpečné pre chemo.', '✅ All parameters safe for chemo.'), lang)
  }
  else {
    text += t(L('⚠️ Pozor: niektoré parametre mimo bezpečného rozsahu. Konzultujte s onkológom.', '⚠️ Warning: some parameters out of safe range. Consult oncologist.'), lang)
  }

  // Safety flags
  const flags = data.safety_flag_status as Record<string, Record<string, unknown>> | undefined
  if (flags) {
    const activeFlags = Object.entries(flags).filter(([, v]) => v?.active)
    if (activeFlags.length) {
      text += `\n\n${t(L('Bezpečnostné varovania:', 'Safety flags:'), lang)}`
      for (const [key] of activeFlags) {
        const name = key.replace(/_/g, ' ')
        text += `\n🚩 ${name}`
      }
    }
  }

  return truncate(text)
}

function formatFamily(data: Record<string, unknown>, lang: Lang): string {
  const updates = (data.updates || []) as Array<Record<string, unknown>>
  if (!updates.length) {
    return t(L(
      'Zatiaľ žiadna správa pre rodinu.\n\nSúhrn sa generuje automaticky.',
      'No family update yet.\n\nThe summary is generated automatically.',
    ), lang)
  }

  const latest = updates[0]!
  const date = latest.date || 'N/A'
  const content = String(latest.content || t(L('Bez obsahu', 'No content'), lang))

  return truncate(`*${t(L('Správa pre rodinu', 'Family Update'), lang)}* (${date})\n\n${content}`)
}

function formatQuestions(data: Record<string, unknown>, lang: Lang): string {
  const briefings = (data.briefings || []) as Array<Record<string, unknown>>
  if (!briefings.length) {
    return t(L(
      'Žiadne otázky pre onkológa.\n\nOtázky sa generujú z denného briefingu.',
      'No questions for oncologist.\n\nQuestions are generated from the daily briefing.',
    ), lang)
  }

  const latest = briefings[0]!
  const content = String(latest.content || latest.summary || '')
  const date = latest.date || latest.created_at || ''

  // Extract "Questions for oncologist" section from briefing content
  const questionsMatch = content.match(/(?:Otázky pre onkológa|Questions for (?:the )?oncologist)[:\s]*\n([\s\S]*?)(?:\n\n|\n#|$)/i)
  if (questionsMatch?.[1]) {
    return truncate(`*${t(L('Otázky pre onkológa', 'Questions for Oncologist'), lang)}* (${date})\n\n${questionsMatch[1].trim()}`)
  }

  // Fallback: check for numbered questions pattern anywhere
  const lines = content.split('\n')
  const questionLines = lines.filter(l => /^\s*\d+[\.\)]\s/.test(l) && l.includes('?'))
  if (questionLines.length) {
    return truncate(`*${t(L('Otázky pre onkológa', 'Questions for Oncologist'), lang)}* (${date})\n\n${questionLines.join('\n')}`)
  }

  return t(L(
    'V poslednom briefingu neboli nájdené otázky pre onkológa.',
    'No questions for oncologist found in the latest briefing.',
  ), lang)
}

const TOXICITY_GRADES: Record<string, string> = {
  '0': '✅ 0', '1': '🟡 1', '2': '🟠 2', '3': '🔴 3', '4': '🔴 4',
}

function formatToxicity(data: Record<string, unknown>, lang: Lang): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  if (!entries.length) {
    return t(L('Žiadne záznamy toxicity.', 'No toxicity records.'), lang)
  }

  let text = t(L('*Toxicita*\n', '*Toxicity*\n'), lang)
  for (const entry of entries.slice(0, 3)) {
    const date = entry.date || 'N/A'
    let meta = entry.metadata as Record<string, unknown> | string
    if (typeof meta === 'string') {
      try { meta = JSON.parse(meta) } catch { meta = {} }
    }
    if (typeof meta !== 'object' || meta === null) meta = {}

    text += `\n*${date}*\n`
    const params = ['neuropathy', 'diarrhea', 'mucositis', 'fatigue', 'nausea', 'hand_foot']
    for (const p of params) {
      const val = (meta as Record<string, unknown>)[p]
      if (val != null) {
        const grade = TOXICITY_GRADES[String(val)] || String(val)
        const label = p === 'hand_foot' ? 'hand-foot' : p
        text += `${grade} ${label}\n`
      }
    }
    const ecog = (meta as Record<string, unknown>).ecog
    if (ecog != null) text += `ECOG: ${ecog}\n`
  }

  return truncate(text)
}

function formatWeight(data: Record<string, unknown>, lang: Lang): string {
  const entries = (data.entries || []) as Array<Record<string, unknown>>
  if (!entries.length) {
    return t(L('Žiadne záznamy váhy.', 'No weight records.'), lang)
  }

  const baseline = data.baseline_weight_kg as number || 72
  let text = t(L('*Váha*\n', '*Weight*\n'), lang)
  text += `${t(L('Východisko', 'Baseline'), lang)}: ${baseline} kg\n`

  for (const entry of entries.slice(0, 5)) {
    const date = entry.date || 'N/A'
    const weight = entry.weight_kg as number
    if (!weight) continue
    const change = ((weight - baseline) / baseline) * 100
    const icon = change <= -5 ? '🔴' : change <= -3 ? '🟡' : '🟢'
    text += `\n${icon} ${date}: ${weight} kg (${change > 0 ? '+' : ''}${change.toFixed(1)}%)`
  }

  const alerts = (data.alerts || []) as Array<Record<string, unknown>>
  if (alerts.length) {
    text += `\n\n⚠️ ${t(L('Upozornenie: >5% strata hmotnosti', 'Warning: >5% weight loss'), lang)}`
  }

  return truncate(text)
}

function formatDose(data: Record<string, unknown>, lang: Lang): string {
  const drug = data.drug || 'oxaliplatin'
  const cumulative = data.cumulative_mg_m2 as number || 0
  const dosePerCycle = data.dose_per_cycle as number || 85
  const cyclesCounted = data.cycles_counted as number || 0
  const maxRecommended = data.max_recommended as number || 850
  const pctToNext = data.pct_to_next as number || 0
  const nextThreshold = data.next_threshold as Record<string, unknown> | null
  const source = data.data_source === 'extracted' ? '📋' : '🔢'

  let text = t(
    L(`*Kumulatívna dávka ${drug}*\n`, `*Cumulative ${drug} dose*\n`),
    lang,
  )
  text += `\n${source} ${cumulative.toFixed(1)} ${data.unit || 'mg/m²'}`
  text += ` (${cyclesCounted} ${t(L('cyklov', 'cycles'), lang)})\n`
  text += `${t(L('Dávka/cyklus', 'Dose/cycle'), lang)}: ${dosePerCycle} ${data.unit || 'mg/m²'}\n`

  if (nextThreshold) {
    const severity = nextThreshold.severity === 'warning' ? '🟡' : '🔴'
    text += `\n${severity} ${t(L('Ďalší prah', 'Next threshold'), lang)}: ${nextThreshold.at} ${data.unit || 'mg/m²'} (${pctToNext}%)\n`
    text += `   ${nextThreshold.action || ''}\n`
  }

  // Progress bar
  const pct = Math.min((cumulative / maxRecommended) * 100, 100)
  const filled = Math.round(pct / 10)
  const bar = '█'.repeat(filled) + '░'.repeat(10 - filled)
  text += `\n[${bar}] ${pct.toFixed(0)}% ${t(L('z maxima', 'of max'), lang)} (${maxRecommended})`

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

function helpText(lang: Lang, hasMultiplePatients: boolean = true): string {
  const patientLines = hasMultiplePatients
    ? lang === 'en'
      ? '• *patients* / *pacienti* — List patients\n• *switch <slug>* / *prepni <meno>* — Switch patient\n'
      : '• *pacienti* / *patients* — Zoznam pacientov\n• *prepni <meno>* / *switch <slug>* — Prepni pacienta\n'
    : ''

  if (lang === 'en') {
    return `*Oncoteam WhatsApp*

Commands:
• *labs* / *labky* — Latest lab results
• *precycle* / *predcyklus* — Pre-cycle safety check
• *meds* / *lieky* — Medications and compliance
• *cycle* / *cyklus* — Current cycle status
• *family* / *rodina* — Family update summary
• *questions* / *otazky* — Questions for oncologist
• *toxicity* / *toxicita* — Side effects log
• *weight* / *vaha* — Weight trend
• *dose* / *davka* — Cumulative dose
• *trials* / *studie* — Clinical trial matches
• *timeline* / *casovka* — Treatment events
• *briefing* — Latest briefing
• *cost* / *naklady* — AI agent cost & budget
${patientLines}• *status* / *stav* — System status
• *help* / *pomoc* — This help

Sub-commands: labs cea | labs blood | labs liver | labs 2 | timeline chemo | trials all

Send a command or a question.`
  }

  return `*Oncoteam WhatsApp*

Prikazy:
• *labky* / *labs* — Posledne labky
• *predcyklus* / *precycle* — Pred-cyklus kontrola
• *lieky* / *meds* — Lieky a compliance
• *cyklus* / *cycle* — Stav aktualneho cyklu
• *rodina* / *family* — Sprava pre rodinu
• *otazky* / *questions* — Otazky pre onkologa
• *toxicita* / *toxicity* — Vedlajsie ucinky
• *vaha* / *weight* — Trend vahy
• *davka* / *dose* — Kumulativna davka
• *studie* / *trials* — Klinicke studie
• *casovka* / *timeline* — Udalosti liecby
• *briefing* — Posledny briefing
• *naklady* / *cost* — Naklady a rozpocet AI agenta
${patientLines}• *stav* / *status* — Stav systemu
• *pomoc* / *help* — Tento help

Pod-prikazy: labky cea | labky krv | labky pecen | labky 2 | casovka chemo | studie vsetky

Posli prikaz alebo otazku.`
}

export type CommandResult =
  | { type: 'reply'; text: string }
  | { type: 'multi'; segments: string[] }
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
  allowedPatientIds?: string[],
): CommandResult {
  const parts = body.trim().split(/\s+/)
  const slug = parts[1]?.toLowerCase()

  if (!slug) {
    const available = allowedPatientIds?.length ? allowedPatientIds.join(', ') : '?'
    return {
      type: 'reply',
      text: t(L(
        `Pouzitie: *prepni <meno>*\nDostupni: ${available}`,
        `Usage: *switch <slug>*\nAvailable: ${available}`,
      ), lang),
    }
  }

  // Authorization check: only allow switching to authorized patients
  if (allowedPatientIds?.length && !allowedPatientIds.includes(slug)) {
    const available = allowedPatientIds.join(', ')
    return {
      type: 'reply',
      text: t(L(
        `Nemate pristup k pacientovi *${slug}*.\nDostupni pacienti: ${available}`,
        `Access denied to patient *${slug}*.\nAvailable patients: ${available}`,
      ), lang),
    }
  }

  if (fromPhone) {
    setActivePatient(fromPhone.replace(/[\s\-()]/g, ''), slug)
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
  allowedPatientIds?: string[],
): Promise<CommandResult> {
  try {
    const config = useRuntimeConfig()
    const apiKey = config.oncoteamApiKey || ''
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const data = await $fetch<{ patients: Array<{ slug: string; name?: string; doc_count?: number; patient_type?: string; is_current?: boolean }> }>(
      `${oncoteamApiUrl}/api/patients`,
      { headers },
    )

    let patients = data.patients || []
    // Filter by authorized patients if scope is provided
    if (allowedPatientIds?.length) {
      patients = patients.filter(p => allowedPatientIds.includes(p.slug))
    }
    if (!patients.length) {
      return { type: 'reply', text: t(L('Ziadni pacienti.', 'No patients found.'), lang) }
    }

    const current = currentPatientId || getActivePatient(fromPhone?.replace(/[\s\-()]/g, '') || '') || ''
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
  options?: { patientId?: string; allowedPatientIds?: string[]; hasMultiplePatients?: boolean },
): Promise<CommandResult> {
  const { commandWord, subarg } = parseSubCommand(body)
  const lang = detectLang(commandWord)
  const command = COMMAND_MAP[commandWord]

  if (command === 'help') {
    return { type: 'reply', text: helpText(lang, options?.hasMultiplePatients ?? true) }
  }

  // Admin-only: approve command
  if (command === 'approve') {
    return handleApproveCommand(body, oncoteamApiUrl, lang, fromPhone)
  }

  // Patient switching: "prepni q1b" / "switch e5g"
  if (command === 'switch') {
    return handleSwitchCommand(body, lang, fromPhone, options?.allowedPatientIds)
  }

  // List patients: "pacienti" / "patients" — filter by authorized patients
  if (command === 'patients') {
    return handlePatientsCommand(oncoteamApiUrl, lang, fromPhone, options?.patientId, options?.allowedPatientIds)
  }

  // Conversational fallback — handled async (Claude API takes 30-60s,
  // exceeds Twilio's 15s webhook timeout). Caller sends immediate TwiML
  // ack, then sends Claude's response via Twilio REST API.
  if (!command) {
    return { type: 'async', lang, message: body }
  }

  // Increase timeline limit when filtering by type (more data to filter from)
  const timelineLimit = subarg ? 20 : 5
  const apiMap: Record<string, string> = {
    labs: '/api/labs',
    meds: '/api/medications',
    briefing: '/api/briefings?limit=1',
    timeline: `/api/timeline?limit=${timelineLimit}`,
    status: '/api/status',
    cost: '/api/autonomous/cost',
    trials: '/api/research?sort=relevance&per_page=20',
    cycle: '/api/protocol',
    precycle: '/api/protocol',
    family: '/api/family-update?limit=1',
    questions: '/api/briefings?limit=1',
    toxicity: '/api/toxicity?limit=3',
    weight: '/api/weight',
    dose: '/api/cumulative-dose',
  }

  const endpoint = apiMap[command]
  if (!endpoint) return { type: 'reply', text: helpText(lang) }

  try {
    const sep = endpoint.includes('?') ? '&' : '?'
    const config = useRuntimeConfig()
    const apiKey = config.oncoteamApiKey || ''
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    // Include patient_id in API calls for multi-patient support
    const patientId = options?.patientId || 'q1b'
    const data = await $fetch<Record<string, unknown>>(`${oncoteamApiUrl}${endpoint}${sep}lang=${lang}&patient_id=${patientId}`, { headers })

    // Commands that return multi-segment results
    if (command === 'labs') {
      const segments = formatLabs(data, lang, subarg)
      return segments.length > 1
        ? { type: 'multi', segments }
        : { type: 'reply', text: segments[0] || '' }
    }

    let text: string
    switch (command) {
      case 'meds': text = formatMeds(data, lang); break
      case 'briefing': text = formatBriefing(data, lang); break
      case 'timeline': text = formatTimeline(data, lang, subarg); break
      case 'status': text = formatStatus(data, lang); break
      case 'cost': text = formatCost(data, lang); break
      case 'trials': text = formatTrials(data, lang, subarg); break
      case 'cycle': text = formatCycle(data, lang); break
      case 'precycle': text = formatPrecycle(data, lang); break
      case 'family': text = formatFamily(data, lang); break
      case 'questions': text = formatQuestions(data, lang); break
      case 'toxicity': text = formatToxicity(data, lang); break
      case 'weight': text = formatWeight(data, lang); break
      case 'dose': text = formatDose(data, lang); break
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
