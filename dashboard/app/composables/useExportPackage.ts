/**
 * Composable for building and downloading a patient data export package.
 *
 * Fetches selected sections in parallel via Promise.allSettled,
 * applies optional date filtering, and triggers a browser download
 * in JSON or self-contained HTML format.
 */

export interface ExportOptions {
  sections: {
    patient: boolean
    labs: boolean
    timeline: boolean
    protocol: boolean
  }
  dateFrom?: string
  dateTo?: string
  format: 'json' | 'html'
  patientId: string
  lang: string
}

interface ExportState {
  loading: boolean
  error: string | null
  progress: string | null
}

export function useExportPackage() {
  const state = reactive<ExportState>({
    loading: false,
    error: null,
    progress: null,
  })

  const { t } = useI18n()

  async function generateAndDownload(opts: ExportOptions) {
    state.loading = true
    state.error = null
    state.progress = t('export.progressFetching')

    try {
      const qs = new URLSearchParams({
        patient_id: opts.patientId,
        lang: opts.lang,
      }).toString()

      // Build fetch tasks for selected sections
      const tasks: Array<{ key: string; promise: Promise<unknown> }> = []

      if (opts.sections.patient) {
        tasks.push({
          key: 'patient',
          promise: $fetch(`/api/oncoteam/patient?${qs}`),
        })
      }
      if (opts.sections.labs) {
        tasks.push({
          key: 'labs',
          promise: $fetch(`/api/oncoteam/labs?${qs}&limit=200`),
        })
      }
      if (opts.sections.timeline) {
        tasks.push({
          key: 'timeline',
          promise: $fetch(`/api/oncoteam/timeline?${qs}&limit=500`),
        })
      }
      if (opts.sections.protocol) {
        tasks.push({
          key: 'protocol',
          promise: $fetch(`/api/oncoteam/protocol?${qs}`),
        })
      }

      const results = await Promise.allSettled(tasks.map((t) => t.promise))

      // Collect data, noting any partial failures
      const data: Record<string, unknown> = {}
      const errors: string[] = []

      results.forEach((r, i) => {
        const key = tasks[i].key
        if (r.status === 'fulfilled') {
          data[key] = r.value
        } else {
          errors.push(`${key}: ${(r.reason as Error)?.message || 'failed'}`)
        }
      })

      if (Object.keys(data).length === 0) {
        state.error = errors.join('; ') || 'All sections failed to load'
        return
      }

      // Apply client-side date filtering
      if (opts.dateFrom || opts.dateTo) {
        const from = opts.dateFrom || '0000-01-01'
        const to = opts.dateTo || '9999-12-31'

        if (data.labs && Array.isArray((data.labs as Record<string, unknown>).entries)) {
          const labsData = data.labs as Record<string, unknown>
          labsData.entries = (labsData.entries as Array<Record<string, string>>).filter((e) => {
            const d = e.event_date || e.date || ''
            return d >= from && d <= to
          })
        }

        if (data.timeline && Array.isArray((data.timeline as Record<string, unknown>).events)) {
          const tlData = data.timeline as Record<string, unknown>
          tlData.events = (tlData.events as Array<Record<string, string>>).filter((e) => {
            const d = e.event_date || e.date || ''
            return d >= from && d <= to
          })
        }
      }

      state.progress = t('export.progressBuilding')

      const now = new Date().toISOString().slice(0, 10)
      const ext = opts.format === 'json' ? 'json' : 'html'
      const filename = `oncoteam-export-${opts.patientId}-${now}.${ext}`

      let blob: Blob

      if (opts.format === 'json') {
        const pkg = {
          exported_at: new Date().toISOString(),
          patient_id: opts.patientId,
          lang: opts.lang,
          partial_errors: errors.length > 0 ? errors : undefined,
          // #382 — medical-info disclaimer machine-readable alongside the
          // HTML export footer, so downstream consumers (automations, LLM
          // prompts fed this as input) carry the informative-only framing
          // and cannot lose it during re-serialisation.
          _disclaimer: {
            notice: opts.lang === 'sk'
              ? 'Informatívny prehľad — overí ošetrujúci lekár. Oncoteam nie je zdravotnícka pomôcka podľa EÚ MDR 2017/745.'
              : 'Informational overview — verified by the treating physician. Oncoteam is not a medical device under EU MDR 2017/745 or FDA SaMD.',
            full_legal_url: 'https://oncoteam.cloud/pravne-upozornenie.html',
          },
          ...data,
        }
        blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' })
      } else {
        blob = new Blob([buildHtml(data, opts, errors)], { type: 'text/html' })
      }

      // Trigger download
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      state.error = (e as Error)?.message || 'Export failed'
    } finally {
      state.loading = false
      state.progress = null
    }
  }

  return { state, generateAndDownload }
}

// ---------------------------------------------------------------------------
// HTML template builder
// ---------------------------------------------------------------------------

function esc(val: unknown): string {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function buildHtml(
  data: Record<string, unknown>,
  opts: ExportOptions,
  errors: string[],
): string {
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ')

  let sections = ''

  // Patient section
  if (data.patient) {
    const p = data.patient as Record<string, unknown>
    sections += `
    <section>
      <h2>Patient Profile</h2>
      <table>
        <tr><td class="label">Name</td><td>${esc(p.name)}</td></tr>
        <tr><td class="label">Diagnosis</td><td>${esc(p.diagnosis)}</td></tr>
        <tr><td class="label">Stage</td><td>${esc(p.staging)}</td></tr>
        <tr><td class="label">Treatment</td><td>${esc(p.treatment_regimen)}</td></tr>
        <tr><td class="label">ECOG</td><td>${esc(p.ecog)}</td></tr>
      </table>
      ${p.biomarkers ? `<h3>Biomarkers</h3><pre>${esc(JSON.stringify(p.biomarkers, null, 2))}</pre>` : ''}
      ${p.safety_flags && Array.isArray(p.safety_flags) && (p.safety_flags as string[]).length > 0 ? `<h3>Safety Flags</h3><ul>${(p.safety_flags as string[]).map((f) => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
    </section>`
  }

  // Labs section
  if (data.labs) {
    const labs = data.labs as Record<string, unknown>
    const entries = (labs.entries || []) as Array<Record<string, unknown>>
    sections += `
    <section>
      <h2>Lab Results</h2>
      <p>${entries.length} entries</p>
      <table>
        <thead><tr><th>Date</th><th>Values</th><th>Notes</th></tr></thead>
        <tbody>
        ${entries
          .map((e) => {
            const vals = e.values as Record<string, unknown> | undefined
            const vStr = vals
              ? Object.entries(vals)
                  .map(([k, v]) => `${esc(k)}: ${esc(v)}`)
                  .join(', ')
              : ''
            return `<tr><td>${esc(e.event_date || e.date)}</td><td>${esc(vStr)}</td><td>${esc(e.notes || '')}</td></tr>`
          })
          .join('')}
        </tbody>
      </table>
    </section>`
  }

  // Timeline section
  if (data.timeline) {
    const tl = data.timeline as Record<string, unknown>
    const events = (tl.events || []) as Array<Record<string, unknown>>
    sections += `
    <section>
      <h2>Treatment Timeline</h2>
      <p>${events.length} events</p>
      <table>
        <thead><tr><th>Date</th><th>Type</th><th>Title</th><th>Notes</th></tr></thead>
        <tbody>
        ${events
          .map(
            (e) =>
              `<tr><td>${esc(e.event_date || e.date)}</td><td>${esc(e.event_type || e.type)}</td><td>${esc(e.title)}</td><td>${esc(e.notes || '')}</td></tr>`,
          )
          .join('')}
        </tbody>
      </table>
    </section>`
  }

  // Protocol section
  if (data.protocol) {
    const proto = data.protocol as Record<string, unknown>
    sections += `
    <section>
      <h2>Clinical Protocol</h2>
      <pre>${esc(JSON.stringify(proto, null, 2))}</pre>
    </section>`
  }

  const errBlock =
    errors.length > 0
      ? `<div class="warn">Partial errors: ${errors.map((e) => esc(e)).join('; ')}</div>`
      : ''

  return `<!DOCTYPE html>
<html lang="${esc(opts.lang)}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oncoteam Export - ${esc(opts.patientId)} - ${now.slice(0, 10)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'DM Sans', sans-serif; color: #1f2937; line-height: 1.6; max-width: 210mm; margin: 0 auto; padding: 24px; }
  h1 { font-family: 'DM Serif Display', serif; font-size: 24px; color: #0d9488; margin-bottom: 4px; }
  h2 { font-family: 'DM Serif Display', serif; font-size: 18px; color: #0d9488; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #ccfbf1; }
  h3 { font-size: 14px; font-weight: 600; margin: 12px 0 6px; }
  .meta { font-size: 12px; color: #6b7280; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #e5e7eb; }
  th { background: #f0fdfa; font-weight: 600; color: #0d9488; }
  .label { font-weight: 600; width: 140px; color: #374151; }
  pre { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; }
  ul { padding-left: 20px; }
  li { margin: 2px 0; }
  .warn { background: #fef3c7; border: 1px solid #fbbf24; border-radius: 6px; padding: 8px 12px; font-size: 12px; margin: 12px 0; }
  .disclaimer { margin-top: 32px; padding: 14px 16px; border-top: 2px solid #ccfbf1; background: #f0fdfa; border-radius: 0 0 6px 6px; font-size: 11px; line-height: 1.5; color: #374151; }
  .disclaimer strong { color: #0d9488; }
  @media print {
    body { padding: 0; }
    section { break-inside: avoid; }
    .disclaimer { break-before: avoid; page-break-inside: avoid; }
  }
</style>
</head>
<body>
  <h1>Oncoteam Data Export</h1>
  <p class="meta">Patient: ${esc(opts.patientId)} | Exported: ${esc(now)} | Language: ${esc(opts.lang)}</p>
  ${errBlock}
  ${sections}
  <div class="disclaimer">
    ${opts.lang === 'sk'
      ? '<strong>Informatívny prehľad — overí ošetrujúci lekár.</strong> Tento export je agregácia dát vedených v Oncoteame pre účely konzultácie s onkológom. Oncoteam nie je zdravotnícka pomôcka podľa EÚ MDR 2017/745; všetky rozhodnutia o liečbe patria ošetrujúcemu lekárovi. Úplné právne upozornenie: <a href="https://oncoteam.cloud/pravne-upozornenie.html">oncoteam.cloud/pravne-upozornenie.html</a>.'
      : '<strong>Informational overview — verified by the treating physician.</strong> This export aggregates data tracked in Oncoteam to support your oncology visit. Oncoteam is not a medical device under EU MDR 2017/745 or FDA SaMD classification; all treatment decisions rest with the treating physician. Full legal notice: <a href="https://oncoteam.cloud/pravne-upozornenie.html">oncoteam.cloud/pravne-upozornenie.html</a>.'}
  </div>
</body>
</html>`
}
