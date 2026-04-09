<script setup lang="ts">
definePageMeta({ layout: false })

// Static mock data — scrambled, no real patient info
const patient = {
  name: 'Demo Patient',
  treatment_regimen: 'mFOLFOX6 90%',
  current_cycle: 3,
  ecog: '1',
  diagnosis_description: 'Metastatic Colorectal Cancer (mCRC)',
  staging: 'IV',
  biomarkers: {
    KRAS: 'mutant G12X',
    NRAS: 'wild-type',
    BRAF_V600E: 'wild-type',
    HER2: 'negative',
    MSI: 'pMMR / MSS',
  },
}

const labEntries = [
  {
    date: '2026-03-19', values: { ANC: 2800, PLT: 185000, hemoglobin: 11.2, CEA: 95.4, CA_19_9: 4820, WBC: 6.1, creatinine: 0.82 },
    value_statuses: { ANC: 'normal', PLT: 'normal', hemoglobin: 'normal', CEA: 'high', CA_19_9: 'high', WBC: 'normal', creatinine: 'normal' },
    directions: { CEA: 'down', CA_19_9: 'down', ANC: 'up', hemoglobin: 'stable' },
    health_directions: { CEA: 'improving', CA_19_9: 'improving', ANC: 'improving', hemoglobin: 'stable' },
    alerts: [],
  },
  {
    date: '2026-02-27', values: { ANC: 2200, PLT: 165000, hemoglobin: 10.8, CEA: 280.1, CA_19_9: 15230, WBC: 5.4 },
    value_statuses: { ANC: 'normal', PLT: 'normal', hemoglobin: 'normal', CEA: 'high', CA_19_9: 'high', WBC: 'normal' },
    directions: { CEA: 'down', CA_19_9: 'down' },
    health_directions: { CEA: 'improving', CA_19_9: 'improving' },
    alerts: [],
  },
  {
    date: '2026-02-13', values: { ANC: 3100, PLT: 195000, hemoglobin: 11.5, CEA: 450.2, CA_19_9: 28500 },
    value_statuses: { ANC: 'normal', PLT: 'normal', hemoglobin: 'normal', CEA: 'high', CA_19_9: 'high' },
    directions: {},
    health_directions: {},
    alerts: [],
  },
]

const KEY_PARAMS = [
  { key: 'ANC', label: 'ANC', unit: '/\u00b5L' },
  { key: 'PLT', label: 'PLT', unit: '/\u00b5L' },
  { key: 'hemoglobin', label: 'HGB', unit: 'g/dL' },
  { key: 'CEA', label: 'CEA', unit: 'ng/mL' },
  { key: 'CA_19_9', label: 'CA 19-9', unit: 'U/mL' },
]

const ALL_LAB_PARAMS = [
  { key: 'WBC', label: 'WBC', unit: '\u00d710\u00b3/\u00b5L', refLow: 4.0, refHigh: 10.0 },
  { key: 'ANC', label: 'ANC', unit: '/\u00b5L', refLow: 1500, refHigh: 7500 },
  { key: 'ABS_LYMPH', label: 'Lymphocytes', unit: '/\u00b5L', refLow: 1000, refHigh: 4000 },
  { key: 'PLT', label: 'Platelets', unit: '\u00d710\u00b3/\u00b5L', refLow: 150, refHigh: 400, divisor: 1000 },
  { key: 'hemoglobin', label: 'Hemoglobin', unit: 'g/dL', refLow: 12.0, refHigh: 17.5 },
  { key: 'creatinine', label: 'Creatinine', unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  { key: 'CEA', label: 'CEA', unit: 'ng/mL', refLow: 0, refHigh: 5.0, tumor: true },
  { key: 'CA_19_9', label: 'CA 19-9', unit: 'U/mL', refLow: 0, refHigh: 37, tumor: true },
  { key: 'SII', label: 'SII', unit: '', refLow: 0, refHigh: 1800, computed: true },
  { key: 'NE_LY', label: 'Ne/Ly Ratio', unit: '', refLow: 0, refHigh: 3.0, computed: true },
] as const

type LabParam = (typeof ALL_LAB_PARAMS)[number]

const labEntriesFull = labEntries.map((e) => {
  const vals = { ...e.values } as Record<string, number | undefined>
  if (!vals.ABS_LYMPH) {
    if (e.date === '2026-03-19') vals.ABS_LYMPH = 1400
    else if (e.date === '2026-02-27') vals.ABS_LYMPH = 1100
    else vals.ABS_LYMPH = 1500
  }
  if (vals.ANC && vals.PLT && vals.ABS_LYMPH) {
    vals.SII = Math.round((vals.ANC * vals.PLT) / vals.ABS_LYMPH)
  }
  if (vals.ANC && vals.ABS_LYMPH) {
    vals.NE_LY = Math.round((vals.ANC / vals.ABS_LYMPH) * 100) / 100
  }
  return { ...e, values: vals }
})

function formatLabVal(val: number | undefined, param: LabParam) {
  if (val == null) return '\u2014'
  const v = 'divisor' in param && param.divisor ? val / param.divisor : val
  if (v >= 1000) return (v / 1000).toFixed(1) + 'k'
  if (Number.isInteger(v)) return String(v)
  return v.toFixed(1)
}

function labStatus(val: number | undefined, param: LabParam): 'low' | 'high' | 'normal' {
  if (val == null) return 'normal'
  const v = 'divisor' in param && param.divisor ? val / param.divisor : val
  if (v < param.refLow) return 'low'
  if (v > param.refHigh) return 'high'
  return 'normal'
}

function labStatusClass(status: 'low' | 'high' | 'normal') {
  if (status === 'high') return 'text-amber-600 font-semibold'
  if (status === 'low') return 'text-blue-600 font-semibold'
  return 'text-gray-900'
}

function pctChange(current: number | undefined, previous: number | undefined): string {
  if (current == null || previous == null || previous === 0) return ''
  const pct = ((current - previous) / previous) * 100
  const sign = pct > 0 ? '+' : ''
  return sign + pct.toFixed(0) + '%'
}

const timelineEvents = [
  { event_type: 'chemotherapy', title: 'Cycle 4 — mFOLFOX6', event_date: '2026-04-02' },
  { event_type: 'lab_result', title: 'Pre-cycle labs', event_date: '2026-03-31' },
  { event_type: 'consultation', title: 'Oncology follow-up', event_date: '2026-04-10' },
]

const agents = [
  { name: 'Daily Research', schedule: 'Daily 09:00', last_run: '2h ago', category: 'research' },
  { name: 'Trial Monitor', schedule: 'Daily 07:45', last_run: '4h ago', category: 'research' },
  { name: 'Pre-cycle Check', schedule: 'Before each cycle', last_run: '5d ago', category: 'clinical' },
  { name: 'Weekly Briefing', schedule: 'Mon 05:00', last_run: '2d ago', category: 'reporting' },
  { name: 'Lab Sync', schedule: 'Every 5h', last_run: '1h ago', category: 'data_pipeline' },
  { name: 'Cost Report', schedule: 'Daily 06:00', last_run: '6h ago', category: 'reporting' },
]

const CATEGORY_COLORS: Record<string, string> = {
  research: 'bg-purple-100 text-purple-700',
  clinical: 'bg-red-100 text-red-700',
  reporting: 'bg-green-100 text-green-700',
  data_pipeline: 'bg-blue-100 text-blue-700',
}

const EVENT_ICONS: Record<string, string> = {
  chemotherapy: '\uD83D\uDC89',
  lab_result: '\uD83E\uDDEA',
  consultation: '\uD83D\uDC68\u200D\u2695\uFE0F',
}

function directionIcon(dir: string | undefined) {
  if (dir === 'up') return '\u2191'
  if (dir === 'down') return '\u2193'
  return '\u2192'
}

function healthColor(hd: string | undefined) {
  if (hd === 'improving') return 'text-emerald-600'
  if (hd === 'worsening') return 'text-red-600'
  return 'text-gray-500'
}

const demoView = ref<'overview' | 'labs' | 'research' | 'protocol'>('overview')

const safetyFlags = [
  { label: 'Anti-EGFR with KRAS mutation', rule: 'NEVER — permanently contraindicated', active: true, severity: 'permanent' },
  { label: 'Bevacizumab with active VTE', rule: 'HIGH RISK — requires oncologist discussion', active: true, severity: 'high' },
  { label: 'Oxaliplatin with grade 3 neuropathy', rule: 'HOLD oxaliplatin, continue 5-FU/LV', active: false, severity: 'conditional' },
]

const funnelTrials = [
  { id: 'NCT07221357', title: 'Pumitamig + Chemo vs Bev + Chemo (1L mCRC)', stage: 'Watching' },
  { id: 'NCT06973564', title: 'JAB-23E73 pan-KRAS inhibitor', stage: 'Watching' },
  { id: 'NCT07284849', title: 'INCA33890 + FOLFOX + Bev (1L MSS mCRC)', stage: 'Eligible Now' },
  { id: 'NCT05253651', title: 'Tucatinib + Tras + FOLFOX (HER2+ mCRC)', stage: 'Excluded' },
]
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb]">
    <!-- Demo banner -->
    <div class="bg-gradient-to-r from-teal-600 to-cyan-700 text-white px-4 py-2.5 text-center text-sm">
      <span class="font-semibold">Demo Mode</span> — This is a demo with sample data. No real patient information.
      <a href="https://oncoteam.cloud" class="ml-3 underline font-medium hover:text-teal-100">Back to oncoteam.cloud</a>
      <span class="mx-1 opacity-50">|</span>
      <NuxtLink to="/login" class="underline font-medium hover:text-teal-100">Sign in</NuxtLink>
    </div>

    <div class="max-w-6xl mx-auto px-4 py-6 space-y-5">
      <!-- Header -->
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-teal-600 to-cyan-700 flex items-center justify-center shadow-sm">
          <span class="text-sm text-white font-bold">+</span>
        </div>
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Oncoteam <span class="text-sm font-normal text-gray-400">demo</span></h1>
          <p class="text-sm text-gray-500">{{ patient.name }} — Treatment overview</p>
        </div>
      </div>

      <!-- View tabs -->
      <div class="flex gap-1 rounded-lg border border-gray-200 p-1 bg-gray-50 w-fit">
        <button v-for="v in ['overview', 'labs', 'research', 'protocol']" :key="v"
          class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          :class="demoView === v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          @click="demoView = v as any"
        >{{ v.charAt(0).toUpperCase() + v.slice(1) }}</button>
      </div>

      <!-- Protocol view -->
      <div v-if="demoView === 'protocol'" class="space-y-3">
        <h2 class="text-sm font-semibold text-gray-700">Safety Flags</h2>
        <div v-for="(flag, i) in safetyFlags" :key="i"
          class="rounded-lg border p-4"
          :class="flag.active ? 'border-red-300 bg-red-50/50 ring-1 ring-red-200' : 'border-gray-200 bg-white opacity-60'"
        >
          <div class="flex items-center gap-2 mb-1">
            <span class="text-sm font-medium" :class="flag.active ? 'text-red-900' : 'text-gray-600'">{{ flag.label }}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full font-semibold" :class="flag.active ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'">
              {{ flag.active ? (flag.severity === 'permanent' ? 'PERMANENT' : 'ACTIVE') : 'Clear' }}
            </span>
          </div>
          <div class="text-xs text-gray-500">{{ flag.rule }}</div>
        </div>
      </div>

      <!-- Research/Funnel view -->
      <div v-if="demoView === 'research'" class="space-y-3">
        <h2 class="text-sm font-semibold text-gray-700">Trial Funnel</h2>
        <div class="flex gap-3 overflow-x-auto pb-2">
          <div v-for="stage in ['Excluded', 'Watching', 'Eligible Now']" :key="stage"
            class="w-56 flex-shrink-0 rounded-xl border border-gray-200 bg-gray-50/50 p-3"
          >
            <div class="text-xs font-semibold text-gray-600 mb-2">{{ stage }}</div>
            <div v-for="t in funnelTrials.filter(t => t.stage === stage)" :key="t.id"
              class="rounded-lg border border-gray-200 bg-white p-2.5 mb-2 text-xs"
            >
              <div class="font-mono text-teal-700 text-[10px]">{{ t.id }}</div>
              <div class="text-gray-800 mt-0.5">{{ t.title }}</div>
            </div>
            <div v-if="!funnelTrials.filter(t => t.stage === stage).length" class="text-[10px] text-gray-400 text-center py-4">No trials</div>
          </div>
        </div>
      </div>

      <!-- Labs view — full comparison table -->
      <div v-if="demoView === 'labs'" class="space-y-4">
        <!-- Summary cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="rounded-xl border border-gray-200 bg-white p-4 text-center">
            <div class="text-[10px] font-medium text-gray-400 uppercase">Entries</div>
            <div class="text-2xl font-bold text-gray-900">{{ labEntriesFull.length }}</div>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-4 text-center">
            <div class="text-[10px] font-medium text-gray-400 uppercase">SII (latest)</div>
            <div class="text-2xl font-bold" :class="(labEntriesFull[0].values.SII ?? 0) > 1800 ? 'text-amber-600' : 'text-emerald-600'">
              {{ labEntriesFull[0].values.SII?.toLocaleString() ?? '\u2014' }}
            </div>
            <div class="text-[10px] text-gray-400">ref &lt;1800</div>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-4 text-center">
            <div class="text-[10px] font-medium text-gray-400 uppercase">CEA trend</div>
            <div class="text-2xl font-bold text-emerald-600">&darr; {{ pctChange(labEntriesFull[0].values.CEA, labEntriesFull[2].values.CEA) }}</div>
            <div class="text-[10px] text-gray-400">from baseline</div>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-4 text-center">
            <div class="text-[10px] font-medium text-gray-400 uppercase">CA 19-9 trend</div>
            <div class="text-2xl font-bold text-emerald-600">&darr; {{ pctChange(labEntriesFull[0].values.CA_19_9, labEntriesFull[2].values.CA_19_9) }}</div>
            <div class="text-[10px] text-gray-400">from baseline</div>
          </div>
        </div>

        <!-- CBC Delta Table -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="px-5 py-3 border-b border-gray-100 bg-gray-50/50">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-500">Lab Values Comparison</h2>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-100">
                  <th class="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-400">Parameter</th>
                  <th class="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-400">Reference</th>
                  <th v-for="entry in labEntriesFull" :key="entry.date" class="px-4 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                    {{ entry.date }}
                  </th>
                  <th class="px-4 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-gray-400">Change</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(section, si) in [
                  { title: 'Hematology', params: ALL_LAB_PARAMS.filter(p => !('tumor' in p && p.tumor) && !('computed' in p && p.computed)) },
                  { title: 'Tumor Markers', params: ALL_LAB_PARAMS.filter(p => 'tumor' in p && p.tumor) },
                  { title: 'Computed Indices', params: ALL_LAB_PARAMS.filter(p => 'computed' in p && p.computed) },
                ]" :key="si">
                  <tr class="bg-gray-50/70">
                    <td :colspan="3 + labEntriesFull.length" class="px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-500">{{ section.title }}</td>
                  </tr>
                  <tr v-for="param in section.params" :key="param.key" class="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td class="px-4 py-2">
                      <div class="font-medium text-gray-700">{{ param.label }}</div>
                      <div v-if="param.unit" class="text-[10px] text-gray-400">{{ param.unit }}</div>
                    </td>
                    <td class="px-4 py-2 text-xs text-gray-400">{{ param.refLow }}&ndash;{{ param.refHigh }}</td>
                    <td v-for="entry in labEntriesFull" :key="entry.date" class="px-4 py-2 text-right tabular-nums"
                      :class="labStatusClass(labStatus(entry.values[param.key] as number | undefined, param))">
                      {{ formatLabVal(entry.values[param.key] as number | undefined, param) }}
                    </td>
                    <td class="px-4 py-2 text-right text-xs tabular-nums"
                      :class="(() => {
                        const cur = labEntriesFull[0].values[param.key] as number | undefined
                        const prev = labEntriesFull[labEntriesFull.length - 1].values[param.key] as number | undefined
                        if (cur == null || prev == null) return 'text-gray-300'
                        const isMarker = 'tumor' in param && param.tumor
                        const pct = ((cur - prev) / prev) * 100
                        if (isMarker) return pct < -10 ? 'text-emerald-600 font-medium' : pct > 10 ? 'text-red-600 font-medium' : 'text-gray-500'
                        return Math.abs(pct) < 10 ? 'text-gray-500' : labStatus(cur, param) !== 'normal' ? 'text-amber-600 font-medium' : 'text-gray-500'
                      })()">
                      {{ pctChange(labEntriesFull[0].values[param.key] as number | undefined, labEntriesFull[labEntriesFull.length - 1].values[param.key] as number | undefined) || '\u2014' }}
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Alerts -->
        <div class="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
          <span>All hematology values within safe ranges. Tumor markers showing excellent treatment response.</span>
        </div>
      </div>

      <!-- Overview (default) -->
      <template v-if="demoView === 'overview'">
      <!-- No alerts (good) -->
      <div class="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
        <span>All lab values within safe ranges. No alerts.</span>
      </div>

      <!-- Treatment Status + Labs grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Treatment Status -->
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Treatment Status</h2>
          <div class="space-y-3">
            <div class="flex items-baseline justify-between">
              <span class="text-2xl font-bold text-gray-900">{{ patient.treatment_regimen }}</span>
              <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Cycle {{ patient.current_cycle }}</span>
            </div>
            <div class="text-sm text-gray-600">{{ patient.diagnosis_description }}</div>
            <div class="flex gap-4 text-xs text-gray-500">
              <span>Staging: <strong class="text-gray-700">{{ patient.staging }}</strong></span>
              <span>ECOG: <strong class="text-gray-700">{{ patient.ecog }}</strong></span>
            </div>
          </div>
        </div>

        <!-- Recent Labs -->
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">Recent Labs</h2>
            <span class="text-xs text-gray-400">{{ labEntries[0].date }}</span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <div v-for="p in KEY_PARAMS" :key="p.key" class="rounded-lg bg-gray-50 px-3 py-2 text-center">
              <div class="text-[10px] font-medium text-gray-400 uppercase">{{ p.label }}</div>
              <div class="text-lg font-bold" :class="labEntries[0].value_statuses?.[p.key] === 'high' ? 'text-amber-600' : 'text-gray-900'">
                {{ labEntries[0].values?.[p.key] != null ? (labEntries[0].values[p.key] > 1000 ? (labEntries[0].values[p.key] / 1000).toFixed(1) + 'k' : labEntries[0].values[p.key].toFixed?.(1) ?? labEntries[0].values[p.key]) : '\u2014' }}
              </div>
              <div class="text-xs" :class="healthColor(labEntries[0].health_directions?.[p.key])">
                {{ directionIcon(labEntries[0].directions?.[p.key]) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Biomarkers -->
      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Molecular Profile</h2>
        <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div v-for="(val, key) in patient.biomarkers" :key="key" class="rounded-lg bg-gray-50 px-3 py-2">
            <div class="text-[10px] font-medium text-gray-400 uppercase">{{ key }}</div>
            <div class="text-sm font-medium text-gray-900 mt-0.5">{{ val }}</div>
          </div>
        </div>
      </div>

      <!-- Upcoming + Agents grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Upcoming Events -->
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Upcoming</h2>
          <div class="space-y-2">
            <div v-for="evt in timelineEvents" :key="evt.title" class="flex items-center gap-3 text-sm">
              <span class="text-base">{{ EVENT_ICONS[evt.event_type] || '\uD83D\uDCC5' }}</span>
              <span class="text-gray-700 flex-1">{{ evt.title }}</span>
              <span class="text-xs text-gray-400 whitespace-nowrap">{{ evt.event_date }}</span>
            </div>
          </div>
        </div>

        <!-- Agents -->
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Autonomous Agents</h2>
          <div class="space-y-2">
            <div v-for="agent in agents" :key="agent.name" class="flex items-center justify-between text-sm">
              <div class="flex items-center gap-2">
                <span class="text-gray-700">{{ agent.name }}</span>
                <span class="px-1.5 py-0.5 rounded text-[10px] font-medium" :class="CATEGORY_COLORS[agent.category]">{{ agent.category }}</span>
              </div>
              <div class="flex items-center gap-3 text-xs text-gray-400">
                <span>{{ agent.schedule }}</span>
                <span>{{ agent.last_run }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tumor Marker Chart placeholder -->
      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Tumor Markers Trend</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-left text-gray-500 border-b border-gray-200">
                <th class="px-3 py-2">Date</th>
                <th class="px-3 py-2">CEA (ng/mL)</th>
                <th class="px-3 py-2">CA 19-9 (U/mL)</th>
                <th class="px-3 py-2">ANC (/uL)</th>
                <th class="px-3 py-2">HGB (g/dL)</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr v-for="entry in labEntries" :key="entry.date" class="text-gray-700">
                <td class="px-3 py-2 font-mono">{{ entry.date }}</td>
                <td class="px-3 py-2 tabular-nums">{{ entry.values.CEA?.toLocaleString() ?? '\u2014' }}</td>
                <td class="px-3 py-2 tabular-nums">{{ entry.values.CA_19_9?.toLocaleString() ?? '\u2014' }}</td>
                <td class="px-3 py-2 tabular-nums">{{ entry.values.ANC?.toLocaleString() ?? '\u2014' }}</td>
                <td class="px-3 py-2 tabular-nums">{{ entry.values.hemoglobin ?? '\u2014' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="mt-3 flex items-center gap-4 text-xs text-gray-500">
          <span class="flex items-center gap-1"><span class="text-emerald-600 font-bold">&darr;</span> CEA -62% since baseline</span>
          <span class="flex items-center gap-1"><span class="text-emerald-600 font-bold">&darr;</span> CA 19-9 -83% since baseline</span>
          <span class="font-medium text-emerald-600">Excellent treatment response</span>
        </div>
      </div>

      <!-- CTA -->
      <div class="rounded-xl border border-teal-200 bg-gradient-to-r from-teal-50 to-cyan-50 p-6 text-center">
        <h2 class="text-lg font-bold text-gray-900 mb-2">Ready to try Oncoteam?</h2>
        <p class="text-sm text-gray-600 mb-4 max-w-lg mx-auto">
          Oncoteam is an AI-powered treatment intelligence platform for cancer care teams.
          It tracks labs, manages clinical trials, and provides autonomous research briefings.
        </p>
        <div class="flex items-center justify-center gap-3">
          <NuxtLink to="/login" class="px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 transition-colors">
            Sign in with Google
          </NuxtLink>
          <a href="https://oncoteam.cloud" class="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors">
            Learn more
          </a>
        </div>
      </div>

      </template>

      <!-- Footer -->
      <div class="text-center text-xs text-gray-400 py-4">
        Oncoteam &mdash; AI-powered cancer treatment intelligence.
        All demo data is fictional. No real patient information is displayed.
      </div>
    </div>
  </div>
</template>
