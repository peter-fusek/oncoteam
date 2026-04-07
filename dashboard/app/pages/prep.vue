<script setup lang="ts">
const { isGeneralHealth } = usePatientType()

watchEffect(() => {
  if (isGeneralHealth.value) navigateTo('/')
})

const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

// Fetch all data in parallel (lazy, non-blocking)
const { data: patient, status: patientStatus, error: patientError } = fetchApi<Record<string, any>>('/patient', { lazy: true, server: false })
const { data: protocol } = fetchApi<Record<string, any>>('/protocol', { lazy: true, server: false })
const { data: toxicity } = fetchApi<{ entries: Array<Record<string, any>>; total: number }>('/toxicity?limit=5', { lazy: true, server: false })
const { data: labs } = fetchApi<{ entries: Array<Record<string, any>>; total: number }>('/labs?limit=5', { lazy: true, server: false })
const { data: briefings } = fetchApi<{ briefings: Array<Record<string, any>>; total: number }>('/briefings?limit=3', { lazy: true, server: false })
const { data: research } = fetchApi<{ entries: Array<Record<string, any>>; total: number }>('/research?limit=10', { lazy: true, server: false })

// Latest toxicity entry
const latestToxicity = computed(() => toxicity.value?.entries?.[0] ?? null)

// Latest labs
const latestLabs = computed(() => labs.value?.entries?.[0] ?? null)

// Lab alerts
const labAlerts = computed(() => {
  if (!labs.value?.entries) return []
  return labs.value.entries
    .filter(e => e.alerts?.length)
    .flatMap(e => e.alerts.map((a: any) => ({ ...a, date: e.date })))
    .slice(0, 5)
})

// Questions from briefings
const questions = computed(() => {
  if (!briefings.value?.briefings) return []
  const qs: string[] = []
  for (const b of briefings.value.briefings) {
    const lines = (b.content || '').split('\n')
    let inQ = false
    for (const line of lines) {
      if (line.toLowerCase().includes('questions for oncologist')) { inQ = true; continue }
      if (inQ && line.startsWith('#')) break
      if (inQ && line.trim().startsWith('-')) qs.push(line.trim().replace(/^-\s*/, ''))
    }
  }
  return qs.slice(0, 8)
})

// Upcoming milestones
const upcomingMilestones = computed(() => {
  if (!protocol.value?.milestones) return []
  const cycle = protocol.value.current_cycle ?? 1
  return protocol.value.milestones.filter((m: any) => m.cycle >= cycle).slice(0, 4)
})

// Recent research
const recentResearch = computed(() => research.value?.entries?.slice(0, 5) ?? [])

// Safety flags
const criticalFlags = computed(() => {
  if (!protocol.value?.safety_flags) return []
  return Object.entries(protocol.value.safety_flags)
    .filter(([_, f]: any) => f.rule.includes('NEVER') || f.rule.includes('HIGH RISK'))
    .map(([id, f]: any) => ({ id, ...f }))
})

// Excluded therapies (normalize dict vs list format)
const excludedTherapies = computed(() => {
  const raw = patient.value?.excluded_therapies
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return Object.entries(raw).map(([therapy, reason]) => ({ therapy, reason }))
})

// Print-friendly
const drilldown = useDrilldown()

function printPrep() {
  window.print()
}
</script>

<template>
  <div class="space-y-6 print:space-y-4 print:text-black">
    <div class="flex items-center justify-between print:hidden">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('prep.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('prep.subtitle') }}</p>
      </div>
      <UButton icon="i-lucide-printer" variant="outline" size="xs" color="neutral" @click="printPrep">
        {{ $t('common.print') }}
      </UButton>
    </div>

    <!-- Print header -->
    <div class="hidden print:block">
      <h1 class="text-xl font-bold">{{ $t('prep.printHeader') }}</h1>
      <p class="text-sm text-gray-500">{{ new Date().toLocaleDateString('sk-SK') }}</p>
    </div>

    <SkeletonLoader v-if="!patient && patientStatus === 'pending'" variant="card" />
    <ApiErrorBanner v-else-if="patientStatus === 'error'" :error="patientError?.message || 'Failed to load prep data'" />
    <template v-else>
    <!-- Patient Summary -->
    <div class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.sectionPatient') }}</h2>
      <div class="grid grid-cols-2 gap-2 text-sm print:text-black">
        <div><span class="text-gray-500">{{ $t('prep.labelName') }}</span> <span class="text-gray-900 print:text-black">{{ patient?.name }}</span></div>
        <div><span class="text-gray-500">{{ $t('prep.labelDiagnosis') }}</span> <span class="text-gray-900 print:text-black">{{ patient?.diagnosis_description }}</span></div>
        <div><span class="text-gray-500">{{ $t('prep.labelRegimen') }}</span> <span class="text-gray-900 print:text-black">{{ patient?.treatment_regimen }}</span></div>
        <div><span class="text-gray-500">{{ $t('prep.labelCycle') }}</span> <span class="text-gray-900 print:text-black">{{ patient?.current_cycle }}</span></div>
        <div><span class="text-gray-500">{{ $t('prep.labelStaging') }}</span> <span class="text-gray-900 print:text-black">{{ patient?.staging }}</span></div>
        <div><span class="text-gray-500">KRAS:</span> <span class="text-red-600 print:text-red-600">{{ patient?.biomarkers?.KRAS }}</span></div>
      </div>
    </div>

    <!-- Critical Safety Flags -->
    <div v-if="criticalFlags.length" class="rounded-xl border border-red-500/30 bg-red-500/5 p-4 print:border-red-300 print:bg-red-50">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.criticalSafetyFlags') }}</h2>
      <div
        v-for="flag in criticalFlags"
        :key="flag.id"
        class="flex items-start gap-2 py-1 text-sm cursor-pointer hover:bg-red-500/10 rounded px-1 -mx-1 transition-colors print:cursor-default"
        @click="drilldown.open({ type: 'protocol_section', id: `safety-${flag.id}`, label: flag.id.replace(/_/g, ' '), data: { flag: flag.id, rule: flag.rule, source: flag.source, severity: 'critical' } })"
      >
        <UIcon name="i-lucide-triangle-alert" class="text-red-600 shrink-0 mt-0.5 print:hidden" />
        <div class="flex-1">
          <span class="text-gray-900 print:text-black">{{ flag.rule }}</span>
          <span class="text-xs text-gray-500 ml-2">({{ flag.source }})</span>
        </div>
        <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 mt-1 shrink-0 print:hidden" />
      </div>
    </div>

    <!-- Lab Alerts -->
    <div v-if="labAlerts.length" class="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 print:border-amber-300 print:bg-amber-50">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.labAlerts') }}</h2>
      <div v-for="(alert, i) in labAlerts" :key="i" class="text-sm text-amber-600 print:text-amber-600 py-0.5">
        {{ alert.date }}: <span class="font-mono">{{ alert.param }}</span> = {{ alert.value.toLocaleString() }}
        (min: {{ alert.threshold.toLocaleString() }}) — {{ alert.action }}
      </div>
    </div>

    <!-- Latest Labs -->
    <div v-if="latestLabs" class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.latestLabs', { date: formatDate(latestLabs.date) }) }}</h2>
      <div class="grid grid-cols-3 md:grid-cols-4 gap-2 text-sm">
        <div v-for="(val, key) in latestLabs.values" :key="key">
          <span class="text-gray-500 font-mono">{{ key }}:</span>
          <span class="text-gray-900 print:text-black ml-1">{{ typeof val === 'number' ? val.toLocaleString() : val }}</span>
        </div>
      </div>
    </div>

    <!-- Latest Toxicity -->
    <div v-if="latestToxicity" class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.latestToxicity', { date: formatDate(latestToxicity.date) }) }}</h2>
      <div class="grid grid-cols-3 md:grid-cols-6 gap-2 text-sm">
        <div v-for="(val, key) in latestToxicity.metadata" :key="key">
          <span class="text-gray-500">{{ String(key).replace(/_/g, ' ') }}:</span>
          <span class="ml-1 font-medium" :class="(val as number) >= 3 ? 'text-red-600' : (val as number) >= 2 ? 'text-amber-600' : 'text-emerald-600'">
            {{ val }}
          </span>
        </div>
      </div>
      <p v-if="latestToxicity.notes" class="text-xs text-gray-500 mt-1">{{ latestToxicity.notes }}</p>
    </div>

    <!-- Questions for Oncologist -->
    <div v-if="questions.length" class="rounded-xl border border-teal-500/30 bg-teal-500/5 p-4 print:border-teal-300 print:bg-teal-50">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.questionsForOncologist') }}</h2>
      <ol class="space-y-1 text-sm text-gray-700 print:text-black list-decimal list-inside">
        <li v-for="(q, i) in questions" :key="i">{{ q }}</li>
      </ol>
    </div>

    <!-- Upcoming Milestones -->
    <div v-if="upcomingMilestones.length" class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.upcomingMilestones') }}</h2>
      <div
        v-for="m in upcomingMilestones"
        :key="m.action"
        class="flex items-center gap-2 py-1 text-sm cursor-pointer hover:bg-gray-50 rounded px-1 -mx-1 transition-colors print:cursor-default"
        @click="drilldown.open({ type: 'protocol_section', id: `milestone-${m.action}`, label: m.description, data: { cycle: m.cycle, action: m.action, description: m.description, source: 'mFOLFOX6 treatment milestones' } })"
      >
        <UBadge variant="subtle" size="xs" color="warning">C{{ m.cycle }}</UBadge>
        <span class="text-gray-700 print:text-black flex-1">{{ m.description }}</span>
        <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0 print:hidden" />
      </div>
    </div>

    <!-- Recent Research -->
    <div v-if="recentResearch.length" class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.recentResearch') }}</h2>
      <div
        v-for="r in recentResearch"
        :key="r.id"
        class="py-1 text-sm cursor-pointer hover:bg-gray-50 rounded px-1 transition-colors print:cursor-default"
        @click="drilldown.open({ type: 'research', id: r.id, label: r.title })"
      >
        <div class="text-gray-900 print:text-black">{{ r.title }}</div>
        <div class="text-xs text-gray-500">{{ r.source }} &middot; {{ r.date }}</div>
      </div>
    </div>

    <!-- Excluded Therapies Reminder -->
    <div v-if="excludedTherapies.length" class="rounded-xl border border-gray-200 bg-white p-4 print:border-gray-300 print:bg-white">
      <h2 class="text-sm font-semibold text-gray-900 mb-2 print:text-black">{{ $t('prep.excludedTherapiesBiomarker') }}</h2>
      <div
        v-for="(et, i) in excludedTherapies"
        :key="i"
        class="text-sm text-gray-500 print:text-gray-500 py-0.5 cursor-pointer hover:text-gray-700 transition-colors print:cursor-default"
        @click="drilldown.open({ type: 'biomarker', id: `excluded-${i}`, label: et.therapy, data: { therapy: et.therapy, reason: et.reason, status: 'Permanently excluded', source: 'Molecular pathology B26/746963' } })"
      >
        <span class="text-red-600 print:text-red-600">{{ et.therapy }}</span> — {{ et.reason }}
      </div>
    </div>
    </template>
  </div>
</template>
