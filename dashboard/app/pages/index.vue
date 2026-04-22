<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { activeRole } = useUserRole()
const { formatDate } = useFormatDate()
const { t } = useI18n()
const { isOncology, cancerType, setDiagnosisCode } = usePatientType()
const { activePatientId } = useActivePatient()
const { onboarded: waOnboarded, readFlags: readWaFlags, track: trackWa } = useWhatsAppOnboarding()

// WhatsApp wizard — auto-opens on very first Home visit for a user,
// then never again (localStorage flag). Dismissible banner is always visible
// unless explicitly dismissed (30-day cooldown). See useWhatsAppOnboarding.
const waWizardOpen = ref(false)
onMounted(() => {
  readWaFlags()
  if (!waOnboarded.value) {
    waWizardOpen.value = true
    trackWa('wa_promo_viewed', { surface: 'auto-wizard' })
  }
})

// Client-only fetches — server:false prevents SSR from attempting these calls,
// which caused 503 timeouts when oncofiles was slow (16s+ TTFB → Railway edge 503).
// Shell renders instantly from SSR, data fills in via client-side fetches.
const { data: patient, status: patientStatus } = fetchApi<{
  name: string
  treatment_regimen: string
  current_cycle: number
  ecog: string
  diagnosis_code: string
  diagnosis_description: string
  staging: string
  biomarkers: Record<string, string | boolean>
  excluded_therapies: Array<{ therapy: string; reason: string }> | Record<string, string>
  active_therapies?: Array<{ name: string; status: string; warning?: string }>
}>('/patient', { lazy: true, server: false })

const {
  data: labs,
  status: labsStatus,
  error: labsError,
  stale: labsStale,
  cacheAgeMs: labsCacheAgeMs,
} = fetchApi<{
  entries: Array<{
    date: string
    values: Record<string, number>
    alerts: Array<{ param: string; value: number; threshold: number; action: string }>
    value_statuses: Record<string, 'low' | 'high' | 'normal'>
    directions: Record<string, 'up' | 'down' | 'stable'>
    health_directions: Record<string, 'improving' | 'worsening' | 'stable'>
  }>
  total: number
  error?: string
  unavailable?: boolean
}>('/labs?limit=10', { lazy: true, server: false })

const {
  data: briefings,
  status: briefingsStatus,
  stale: briefingsStale,
  cacheAgeMs: briefingsCacheAgeMs,
} = fetchApi<{
  briefings: Array<{
    id: number
    title: string
    content: string
    date: string
    type: string
    tags: string[]
    summary?: string
    action_count?: number
    questions_for_oncologist?: string[]
  }>
  total: number
}>('/briefings?limit=1', { lazy: true, server: false })

const {
  data: timeline,
  status: timelineStatus,
  stale: timelineStale,
  cacheAgeMs: timelineCacheAgeMs,
} = fetchApi<{
  events: Array<{
    id: number
    event_date: string
    event_type: string
    title: string
    cycle?: number
  }>
}>('/timeline?limit=10', { lazy: true, server: false })

// Preventive care screenings (general health patients only).
// Gate the fetch on isOncology: for oncology patients this endpoint is
// irrelevant and only adds load + surface area for failures (#417).
interface PreventiveCareData {
  screenings: Array<{ id: string; name: string; interval_label: string; last_date: string | null; next_due: string | null; status: string }>
  summary: { up_to_date: number; due: number; overdue: number; unknown: number }
}
const preventiveCare = isOncology.value
  ? ref<PreventiveCareData | null>(null)
  : fetchApi<PreventiveCareData>('/preventive-care', { lazy: true, server: false }).data

const screeningAlerts = computed(() => {
  if (!preventiveCare.value?.screenings) return []
  return preventiveCare.value.screenings.filter(s => s.status === 'overdue' || s.status === 'due').slice(0, 5)
})

// System health for degradation banner (#238). Since #424 the breaker state
// comes from `/readiness` (polled centrally by useCircuitBreakerStatus),
// so /diagnostics on every home mount is redundant — dropping it cuts one
// fetch per visit and removes a retry target when the backend is flapping.
const { degraded: systemDegraded } = useCircuitBreakerStatus()

// Computed helpers
// Merge most recent value for each key parameter across all entries
const mergedLabSnapshot = computed(() => {
  if (!labs.value?.entries) return null
  const values: Record<string, number> = {}
  const statuses: Record<string, string> = {}
  const directions: Record<string, string> = {}
  const healthDirs: Record<string, string> = {}
  let latestDate = ''

  for (const e of labs.value.entries) {
    if (!e.values || Object.keys(e.values).length === 0) continue
    if (!latestDate) latestDate = e.date
    for (const p of KEY_PARAMS.value) {
      if (!(p.key in values) && e.values[p.key] != null) {
        values[p.key] = e.values[p.key]
        if (e.value_statuses?.[p.key]) statuses[p.key] = e.value_statuses[p.key]
        if (e.directions?.[p.key]) directions[p.key] = e.directions[p.key]
        if (e.health_directions?.[p.key]) healthDirs[p.key] = e.health_directions[p.key]
      }
    }
  }
  if (!latestDate) return null
  return { date: latestDate, values, value_statuses: statuses, directions, health_directions: healthDirs }
})

const labAlerts = computed(() => {
  // Only show alerts from the latest lab entry to avoid showing resolved past alerts
  if (!labs.value?.entries?.length) return []
  return labs.value.entries[0].alerts || []
})

const latestBriefing = computed(() => briefings.value?.briefings?.[0] ?? null)

const upcomingEvents = computed(() => {
  if (!timeline.value?.events) return []
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  return timeline.value.events
    .filter(e => e.event_date >= today)
    .slice(0, 5)
})

const ONCOLOGY_BASE_PARAMS = [
  { key: 'ANC', label: 'ANC', unit: '/\u00b5L' },
  { key: 'PLT', label: 'PLT', unit: '/\u00b5L' },
  { key: 'hemoglobin', label: 'HGB', unit: 'g/dL' },
]

const COLORECTAL_TUMOR_PARAMS = [
  { key: 'CEA', label: 'CEA', unit: 'ng/mL' },
  { key: 'CA_19_9', label: 'CA 19-9', unit: 'U/mL' },
]

const BREAST_TUMOR_PARAMS = [
  { key: 'CA_15_3', label: 'CA 15-3', unit: 'U/mL' },
  { key: 'CEA', label: 'CEA', unit: 'ng/mL' },
]

const GENERAL_KEY_PARAMS = [
  { key: 'glucose_fasting', label: 'Glucose', unit: 'mmol/L' },
  { key: 'cholesterol_total', label: 'Chol', unit: 'mmol/L' },
  { key: 'TSH', label: 'TSH', unit: 'mIU/L' },
  { key: 'hemoglobin', label: 'HGB', unit: 'g/L' },
  { key: 'creatinine', label: 'Creat', unit: '\u00b5mol/L' },
]

const KEY_PARAMS = computed(() => {
  if (!isOncology.value) return GENERAL_KEY_PARAMS
  const tumor = cancerType.value === 'breast' ? BREAST_TUMOR_PARAMS : COLORECTAL_TUMOR_PARAMS
  return [...ONCOLOGY_BASE_PARAMS, ...tumor]
})

// Update patient type cache when patient data arrives
watch(patient, (p) => {
  if (p?.diagnosis_code) {
    setDiagnosisCode(activePatientId.value, p.diagnosis_code)
  }
})

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

const EVENT_ICONS: Record<string, string> = {
  chemotherapy: '\uD83D\uDC89',
  lab_result: '\uD83E\uDDEA',
  consultation: '\uD83D\uDC68\u200D\u2695\uFE0F',
  imaging: '\uD83D\uDCF7',
  surgery: '\uD83C\uDFE5',
}
</script>

<template>
  <div class="space-y-5">
    <!-- System degradation banner (#238) -->
    <div v-if="systemDegraded" class="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 flex items-center gap-2">
      <UIcon name="i-lucide-server-crash" class="shrink-0" />
      <span>{{ $t('home.systemDegraded') }}</span>
    </div>

    <!-- WhatsApp onboarding promo (#371) -->
    <WhatsAppOnboardingCard @open-wizard="waWizardOpen = true" />
    <WhatsAppWizard v-model="waWizardOpen" />

    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900">{{ $t('home.title') }}</h1>
      <p class="text-sm text-gray-500">{{ patient?.name }} &mdash; {{ $t('home.subtitle') }}</p>
    </div>

    <!-- Alerts -->
    <div v-if="labAlerts.length" class="space-y-2">
      <div
        v-for="alert in labAlerts"
        :key="alert.param"
        class="flex items-center gap-3 rounded-lg border-l-4 border-red-400 bg-red-50 px-4 py-3"
      >
        <UIcon name="i-lucide-alert-triangle" class="h-5 w-5 text-red-500 shrink-0" />
        <div class="text-sm">
          <span class="font-semibold text-red-800">{{ alert.param }}</span>
          <span class="text-red-700"> = {{ alert.value }} ({{ $t('home.threshold') }}: {{ alert.threshold }})</span>
          <span class="text-red-600 ml-2">&mdash; {{ alert.action }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="mergedLabSnapshot" class="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
      <UIcon name="i-lucide-check-circle" class="h-4 w-4" />
      {{ $t('home.noAlerts') }}
    </div>

    <!-- Treatment Status + Recent Labs — 2 column grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Treatment Status (oncology) / Health Overview (general) -->
      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
          {{ isOncology ? $t('home.treatmentStatus') : $t('home.healthOverview', 'Health Overview') }}
        </h2>
        <div v-if="patient" class="space-y-3">
          <template v-if="isOncology">
            <div class="flex items-baseline justify-between">
              <span class="text-2xl font-bold text-gray-900">{{ patient.treatment_regimen }}</span>
              <UBadge variant="subtle" color="info" size="sm">{{ $t('home.cycle') }} {{ patient.current_cycle }}</UBadge>
            </div>
            <div class="text-sm text-gray-600">{{ patient.diagnosis_description }}</div>
            <div class="flex gap-4 text-xs text-gray-500">
              <span>{{ $t('home.staging') }}: <strong class="text-gray-700">{{ patient.staging }}</strong></span>
              <span>ECOG: <strong class="text-gray-700">{{ patient.ecog }}</strong></span>
            </div>
          </template>
          <template v-else>
            <div class="text-lg font-bold text-gray-900">{{ patient.name }}</div>
            <div class="text-sm text-gray-600">{{ patient.diagnosis_description }}</div>
          </template>
        </div>
        <SkeletonLoader v-else variant="lines" />
      </div>

      <!-- Recent Labs -->
      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">{{ $t('home.recentLabs') }}</h2>
          <NuxtLink to="/labs" class="text-xs text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
        </div>
        <div v-if="labsStale" class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2 flex items-center gap-1.5">
          <UIcon name="i-lucide-clock-alert" class="h-3.5 w-3.5 shrink-0" />
          {{ $t('common.showingCached', { minutes: Math.max(1, Math.round(labsCacheAgeMs / 60000)) }) }}
        </div>
        <div v-if="mergedLabSnapshot" class="space-y-2">
          <div class="text-xs text-gray-500 mb-2">{{ formatDate(mergedLabSnapshot.date) }}</div>
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            <div
              v-for="p in KEY_PARAMS"
              :key="p.key"
              class="rounded-lg bg-gray-50 px-3 py-2 text-center"
            >
              <NuxtLink :to="`/dictionary?q=${p.label}`" class="text-[10px] font-medium text-gray-400 uppercase hover:text-teal-600 underline decoration-dotted transition-colors">{{ p.label }}</NuxtLink>
              <div class="text-lg font-bold" :class="mergedLabSnapshot.value_statuses?.[p.key] === 'low' || mergedLabSnapshot.value_statuses?.[p.key] === 'high' ? 'text-red-600' : 'text-gray-900'">
                {{ mergedLabSnapshot.values?.[p.key] != null ? (mergedLabSnapshot.values[p.key] > 1000 ? (mergedLabSnapshot.values[p.key] / 1000).toFixed(1) + 'k' : mergedLabSnapshot.values[p.key].toFixed(1)) : '\u2014' }}
              </div>
              <div class="text-xs" :class="healthColor(mergedLabSnapshot.health_directions?.[p.key])">
                {{ directionIcon(mergedLabSnapshot.directions?.[p.key]) }}
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="labsError || labs?.unavailable || (labsStatus === 'error')" class="text-sm text-gray-500 py-6 text-center space-y-2">
          <UIcon name="i-lucide-wifi-off" class="h-5 w-5 mx-auto text-gray-300" />
          <p>{{ $t('common.dataUnavailable') }}</p>
          <NuxtLink to="/labs" class="text-xs text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
        </div>
        <div v-else-if="labs && !mergedLabSnapshot && labsStatus !== 'pending'" class="text-sm text-gray-500 py-6 text-center">
          <NuxtLink to="/labs" class="text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
        </div>
        <SkeletonLoader v-else variant="cards" />
      </div>
    </div>

    <!-- Latest Briefing (advocate only) -->
    <div v-if="activeRole === 'advocate'" class="rounded-xl border border-gray-200 bg-white p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">{{ $t('home.latestBriefing') }}</h2>
        <NuxtLink to="/briefings" class="text-xs text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
      </div>
      <div v-if="briefingsStale" class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2 flex items-center gap-1.5">
        <UIcon name="i-lucide-clock-alert" class="h-3.5 w-3.5 shrink-0" />
        {{ $t('common.showingCached', { minutes: Math.max(1, Math.round(briefingsCacheAgeMs / 60000)) }) }}
      </div>
      <SkeletonLoader v-if="briefingsStatus === 'pending'" variant="lines" />
      <template v-else-if="latestBriefing">
        <div class="text-sm text-gray-700 line-clamp-3">{{ latestBriefing.content?.slice(0, 300) }}</div>
        <div v-if="latestBriefing.questions_for_oncologist?.length" class="mt-3 flex items-center gap-2 text-xs text-amber-700">
          <UIcon name="i-lucide-message-circle-question" class="h-4 w-4" />
          {{ latestBriefing.questions_for_oncologist.length }} {{ $t('home.questionsForOncologist') }}
        </div>
        <div class="mt-1 text-xs text-gray-400">{{ formatDate(latestBriefing.date) }}</div>
      </template>
      <div v-else class="text-sm text-gray-500 py-3 text-center">{{ $t('common.dataUnavailable') }}</div>
    </div>

    <!-- Preventive Screenings (general health patients only) -->
    <div v-if="!isOncology && preventiveCare" class="rounded-xl border border-gray-200 bg-white p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">{{ $t('home.preventiveScreenings') }}</h2>
        <NuxtLink to="/patient" class="text-xs text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
      </div>
      <!-- Summary badges -->
      <div v-if="preventiveCare.summary" class="flex items-center gap-2 mb-3">
        <UBadge v-if="preventiveCare.summary.overdue" variant="subtle" color="error" size="sm">{{ preventiveCare.summary.overdue }} {{ $t('preventive.overdue') }}</UBadge>
        <UBadge v-if="preventiveCare.summary.due" variant="subtle" color="warning" size="sm">{{ preventiveCare.summary.due }} {{ $t('preventive.due') }}</UBadge>
        <UBadge v-if="preventiveCare.summary.up_to_date" variant="subtle" color="success" size="sm">{{ preventiveCare.summary.up_to_date }} {{ $t('preventive.upToDate') }}</UBadge>
      </div>
      <!-- Due/overdue items -->
      <div v-if="screeningAlerts.length" class="space-y-2">
        <div
          v-for="s in screeningAlerts"
          :key="s.id"
          class="flex items-center gap-3 rounded-lg px-3 py-2"
          :class="s.status === 'overdue' ? 'bg-red-50' : 'bg-amber-50'"
        >
          <UIcon
            :name="s.status === 'overdue' ? 'i-lucide-alert-triangle' : 'i-lucide-clock'"
            class="h-4 w-4 shrink-0"
            :class="s.status === 'overdue' ? 'text-red-500' : 'text-amber-500'"
          />
          <span class="text-sm text-gray-700 flex-1">{{ s.name }}</span>
          <UBadge
            variant="subtle"
            :color="s.status === 'overdue' ? 'error' : 'warning'"
            size="xs"
          >{{ s.status === 'overdue' ? $t('preventive.overdue') : $t('preventive.due') }}</UBadge>
        </div>
      </div>
      <div v-else class="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        <UIcon name="i-lucide-check-circle" class="h-4 w-4" />
        {{ $t('preventive.allUpToDate') }}
      </div>
    </div>

    <!-- Upcoming Events + Quick Links -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Upcoming -->
      <div v-if="activeRole !== 'patient'" class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">{{ $t('home.upcoming') }}</h2>
          <NuxtLink to="/timeline" class="text-xs text-[var(--clinical-primary)] hover:underline">{{ $t('home.viewAll') }}</NuxtLink>
        </div>
        <div v-if="timelineStale" class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2 flex items-center gap-1.5">
          <UIcon name="i-lucide-clock-alert" class="h-3.5 w-3.5 shrink-0" />
          {{ $t('common.showingCached', { minutes: Math.max(1, Math.round(timelineCacheAgeMs / 60000)) }) }}
        </div>
        <div v-if="upcomingEvents.length" class="space-y-2">
          <div
            v-for="evt in upcomingEvents"
            :key="evt.id"
            class="flex items-center gap-3 text-sm"
          >
            <span class="text-base">{{ EVENT_ICONS[evt.event_type] || '\uD83D\uDCC5' }}</span>
            <span class="text-gray-700 flex-1">{{ evt.title }}</span>
            <span class="text-xs text-gray-400 whitespace-nowrap">{{ formatDate(evt.event_date) }}</span>
          </div>
        </div>
        <div v-else class="text-sm text-gray-500 py-3 text-center">{{ $t('home.noUpcoming') }}</div>
      </div>

      <!-- Quick Links -->
      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">{{ $t('home.quickActions') }}</h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <template v-if="activeRole === 'advocate'">
            <NuxtLink v-if="isOncology" to="/toxicity" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-thermometer" class="h-4 w-4 text-gray-400" />
              {{ $t('home.logToxicity') }}
            </NuxtLink>
            <NuxtLink to="/labs" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-test-tube-diagonal" class="h-4 w-4 text-gray-400" />
              {{ $t('home.addLabs') }}
            </NuxtLink>
            <NuxtLink v-if="isOncology" to="/prep" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-file-check" class="h-4 w-4 text-gray-400" />
              {{ $t('home.preCycleCheck') }}
            </NuxtLink>
            <NuxtLink to="/family-update" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-heart-handshake" class="h-4 w-4 text-gray-400" />
              {{ $t('home.generateUpdate') }}
            </NuxtLink>
          </template>
          <template v-else-if="activeRole === 'patient'">
            <NuxtLink v-if="isOncology" to="/toxicity" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-thermometer" class="h-4 w-4 text-gray-400" />
              {{ $t('home.logToxicity') }}
            </NuxtLink>
            <NuxtLink to="/medications" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-pill" class="h-4 w-4 text-gray-400" />
              {{ $t('nav.medications') }}
            </NuxtLink>
            <NuxtLink to="/family-update" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-heart-handshake" class="h-4 w-4 text-gray-400" />
              {{ $t('home.generateUpdate') }}
            </NuxtLink>
            <NuxtLink to="/timeline" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-calendar-clock" class="h-4 w-4 text-gray-400" />
              {{ $t('nav.timeline') }}
            </NuxtLink>
          </template>
          <template v-else>
            <NuxtLink v-if="isOncology" to="/protocol" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-clipboard-check" class="h-4 w-4 text-gray-400" />
              {{ $t('home.viewProtocol') }}
            </NuxtLink>
            <NuxtLink v-if="isOncology" to="/prep" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-file-check" class="h-4 w-4 text-gray-400" />
              {{ $t('home.preCycleCheck') }}
            </NuxtLink>
            <NuxtLink to="/labs" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-test-tube-diagonal" class="h-4 w-4 text-gray-400" />
              {{ $t('nav.labs') }}
            </NuxtLink>
            <NuxtLink to="/research" class="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-100 transition-colors">
              <UIcon name="i-lucide-microscope" class="h-4 w-4 text-gray-400" />
              {{ $t('nav.research') }}
            </NuxtLink>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
