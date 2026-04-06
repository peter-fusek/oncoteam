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

      <!-- Footer -->
      <div class="text-center text-xs text-gray-400 py-4">
        Oncoteam &mdash; AI-powered cancer treatment intelligence.
        All demo data is fictional. No real patient information is displayed.
      </div>
    </div>
  </div>
</template>
