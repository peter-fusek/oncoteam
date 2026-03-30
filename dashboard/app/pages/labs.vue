<script setup lang="ts">
const { fetchApi, postApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()

const { data: labs, status: labsStatus, error: labsError, refresh } = fetchApi<{
  entries: Array<{
    id: number
    date: string
    sync_date?: string
    values: Record<string, number>
    notes: string
    alerts: Array<{ param: string; value: number; threshold: number; action: string }>
    value_statuses: Record<string, 'low' | 'high' | 'normal'>
    directions: Record<string, 'up' | 'down' | 'stable'>
    health_directions: Record<string, 'improving' | 'worsening' | 'stable'>
    suspects: Array<{ param: string; value: number; prev_value: number; pct_change: number; prev_date: string }>
  }>
  reference_ranges: Record<string, { min: number; max: number; unit: string; note?: string }>
  total: number
  error?: string
}>('/labs', { lazy: true, server: false })

const { data: protocol } = fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; action: string }>
}>('/protocol', { lazy: true, server: false })

// Rookie/Pro mode
const proMode = ref(false)

// Lab parameters organized by category
interface LabParam {
  key: string
  label: string
  color: string
  unit: string
  thresholdKey?: string
  healthDirection?: string
}

interface LabCategory {
  id: string
  label: string
  icon: string
  color: string
  params: LabParam[]
}

const categories: LabCategory[] = [
  {
    id: 'tumor_markers',
    label: 'Tumor Markers',
    icon: 'i-lucide-target',
    color: 'text-amber-600',
    params: [
      { key: 'CEA', label: 'CEA', color: '#d97706', unit: 'ng/mL', healthDirection: 'lower_is_better' },
      { key: 'CA_19_9', label: 'CA 19-9', color: '#7c3aed', unit: 'U/mL', healthDirection: 'lower_is_better' },
    ],
  },
  {
    id: 'hematology',
    label: 'Hematology',
    icon: 'i-lucide-droplets',
    color: 'text-rose-600',
    params: [
      { key: 'ANC', label: 'ANC', color: '#0d9488', unit: '/µL', thresholdKey: 'ANC', healthDirection: 'higher_is_better' },
      { key: 'PLT', label: 'Platelets', color: '#2563eb', unit: '/µL', thresholdKey: 'PLT', healthDirection: 'in_range' },
      { key: 'WBC', label: 'WBC', color: '#0891b2', unit: '×10³/µL', healthDirection: 'in_range' },
      { key: 'hemoglobin', label: 'Hemoglobin', color: '#be123c', unit: 'g/dL', healthDirection: 'higher_is_better' },
      { key: 'ABS_LYMPH', label: 'Lymphocytes', color: '#7c3aed', unit: '/µL', healthDirection: 'higher_is_better' },
    ],
  },
  {
    id: 'organ_function',
    label: 'Organ Function',
    icon: 'i-lucide-activity',
    color: 'text-orange-600',
    params: [
      { key: 'creatinine', label: 'Creatinine', color: '#dc2626', unit: 'mg/dL', healthDirection: 'in_range' },
      { key: 'bilirubin', label: 'Bilirubin', color: '#ca8a04', unit: 'mg/dL', healthDirection: 'in_range' },
      { key: 'ALT', label: 'ALT', color: '#ea580c', unit: 'U/L', healthDirection: 'in_range' },
      { key: 'AST', label: 'AST', color: '#db2777', unit: 'U/L', healthDirection: 'in_range' },
    ],
  },
  {
    id: 'indices',
    label: 'Inflammation Indices',
    icon: 'i-lucide-flame',
    color: 'text-slate-600',
    params: [
      { key: 'SII', label: 'SII', color: '#475569', unit: '', healthDirection: 'lower_is_better' },
      { key: 'NE_LY_RATIO', label: 'Ne/Ly', color: '#57534e', unit: '', healthDirection: 'lower_is_better' },
    ],
  },
]

const allLabParams = categories.flatMap(c => c.params)
const rookieKeys = new Set(['CEA', 'CA_19_9', 'ANC', 'PLT', 'WBC', 'hemoglobin'])

const labParams = computed(() => {
  if (proMode.value) return allLabParams
  return allLabParams.filter(p => rookieKeys.has(p.key))
})

const visibleCategories = computed(() => {
  return categories
    .map(cat => ({
      ...cat,
      params: cat.params.filter(p => labParams.value.includes(p)),
    }))
    .filter(cat => cat.params.length > 0)
})

const sortedEntries = computed(() => {
  if (!labs.value?.entries) return []
  return [...labs.value.entries].sort((a, b) => b.date.localeCompare(a.date))
})

// Suspect values across all entries
const allSuspects = computed(() => {
  if (!labs.value?.entries) return []
  return labs.value.entries
    .filter(e => e.suspects?.length)
    .flatMap(e => e.suspects.map(s => ({ ...s, date: e.date })))
})

function directionArrow(entry: any, key: string): string {
  const dir = entry.directions?.[key]
  if (dir === 'up') return '\u2191'
  if (dir === 'down') return '\u2193'
  if (dir === 'stable') return '\u2192'
  return ''
}

function directionColor(entry: any, key: string): string {
  const health = entry.health_directions?.[key]
  if (health === 'improving') return 'text-green-700'
  if (health === 'worsening') return 'text-red-600'
  return 'text-gray-400'
}

function statusIcon(entry: any, key: string): string {
  if (entry.alerts?.some((a: any) => a.param === key)) return 'i-lucide-octagon-alert'
  const status = entry.value_statuses?.[key]
  if (status === 'low' || status === 'high') return 'i-lucide-triangle-alert'
  if (status === 'normal') return 'i-lucide-circle-check'
  return ''
}

function statusIconColor(entry: any, key: string): string {
  if (entry.alerts?.some((a: any) => a.param === key)) return 'text-red-600'
  const status = entry.value_statuses?.[key]
  if (status === 'low' || status === 'high') return 'text-amber-600'
  if (status === 'normal') return 'text-green-600'
  return 'text-gray-300'
}

function cellBgColor(entry: any, key: string): string {
  // Check if this value is a suspect
  if (entry.suspects?.some((s: any) => s.param === key)) return 'bg-amber-50 border-l-2 border-l-amber-400'
  if (entry.alerts?.some((a: any) => a.param === key)) return 'bg-red-50'
  const status = entry.value_statuses?.[key]
  if (status === 'low' || status === 'high') return 'bg-amber-50/50'
  if (status === 'normal' && entry.values?.[key] != null) return 'bg-green-50/30'
  return ''
}

function isSuspect(entry: any, key: string): any {
  return entry.suspects?.find((s: any) => s.param === key)
}

// Chart data in chronological order (oldest → newest, left → right)
const chronologicalEntries = computed(() => [...sortedEntries.value].reverse())
const chartLabels = computed(() => chronologicalEntries.value.map(e => e.date))

function getValues(key: string): (number | null)[] {
  return chronologicalEntries.value.map(e => e.values?.[key] ?? null)
}

function getThreshold(key: string): number | undefined {
  return protocol.value?.lab_thresholds?.[key]?.min
}

function hasData(key: string): boolean {
  return sortedEntries.value.some(e => e.values?.[key] != null)
}

function refRangeText(key: string): string {
  const ref = labs.value?.reference_ranges?.[key]
  if (!ref) return ''
  return `${ref.min.toLocaleString()}–${ref.max.toLocaleString()}`
}

function formValueStatus(key: string): string {
  const val = form.values[key]
  if (val == null || val === '') return 'border-gray-300'
  const ref = labs.value?.reference_ranges?.[key]
  if (!ref) return 'border-gray-300'
  if (Number(val) < ref.min || Number(val) > ref.max) return 'border-amber-500/50'
  return 'border-green-500/30'
}

// Human-readable action labels
const ACTION_LABELS: Record<string, string> = {
  hold_chemo: 'Hold Chemotherapy',
  dose_reduce: 'Reduce Dose',
  monitor: 'Monitor Closely',
  transfuse: 'Consider Transfusion',
  urgent: 'Urgent Review',
  flag_hematology: 'Flag Hematology',
}
function actionLabel(action: string): string {
  return ACTION_LABELS[action] || action.replace(/_/g, ' ')
}

const drilldown = useDrilldown()

const allAlerts = computed(() => {
  if (!labs.value?.entries) return []
  return labs.value.entries
    .filter(e => e.alerts?.length)
    .flatMap(e => e.alerts.map(a => ({ ...a, date: e.date })))
})

// Lab entry form
const form = reactive({
  date: new Date().toISOString().slice(0, 10),
  notes: '',
  values: {} as Record<string, number | null>,
})

const showForm = ref(false)
const submitting = ref(false)
const submitMsg = ref('')

async function submitLab() {
  submitting.value = true
  submitMsg.value = ''
  const cleanValues: Record<string, number> = {}
  for (const [k, v] of Object.entries(form.values)) {
    if (v != null && v !== '') cleanValues[k] = Number(v)
  }
  try {
    await postApi('/labs', { date: form.date, values: cleanValues, notes: form.notes })
    submitMsg.value = 'saved'
    showForm.value = false
    form.values = {}
    form.notes = ''
    form.date = new Date().toISOString().slice(0, 10)
    await refresh()
  } catch (e: any) {
    submitMsg.value = `error:${e.message || e}`
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('labs.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('labs.subtitle', { count: labs?.total ?? 0 }) }}</p>
        <LastUpdated :timestamp="labs?.last_updated" />
      </div>
      <div class="flex items-center gap-2">
        <!-- Rookie/Pro toggle -->
        <div class="flex rounded-lg border border-gray-200 overflow-hidden shadow-sm">
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="!proMode ? 'bg-teal-600 text-white' : 'bg-white text-gray-500 hover:text-gray-700 hover:bg-gray-50'"
            @click="proMode = false"
          >
            {{ $t('labs.rookie') }}
          </button>
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="proMode ? 'bg-teal-600 text-white' : 'bg-white text-gray-500 hover:text-gray-700 hover:bg-gray-50'"
            @click="proMode = true"
          >
            {{ $t('labs.pro') }}
          </button>
        </div>
        <UButton
          :icon="showForm ? 'i-lucide-x' : 'i-lucide-plus'"
          :variant="showForm ? 'outline' : 'solid'"
          size="xs"
          :color="showForm ? 'neutral' : 'primary'"
          @click="showForm = !showForm"
        >
          {{ showForm ? $t('common.cancel') : $t('labs.addLabs') }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="labs?.error || labsError?.message" />
    <SkeletonLoader v-if="!labs && labsStatus === 'pending'" variant="table" />

    <!-- Suspect Values Warning -->
    <div v-if="allSuspects.length" class="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div class="flex items-center gap-2 mb-2">
        <UIcon name="i-lucide-shield-alert" class="text-amber-600 w-5 h-5" />
        <span class="text-sm font-semibold text-amber-900">Data Verification Required</span>
      </div>
      <div class="space-y-1.5">
        <div v-for="(suspect, i) in allSuspects" :key="i" class="text-xs flex items-center gap-2 text-amber-800">
          <span class="text-amber-500 font-mono">{{ suspect.date }}</span>
          <NuxtLink :to="`/dictionary?q=${suspect.param}`" class="font-semibold underline decoration-dotted hover:text-amber-900">{{ suspect.param }}</NuxtLink>
          <span>{{ Number(suspect.prev_value).toLocaleString() }} → {{ Number(suspect.value).toLocaleString() }}</span>
          <UBadge color="warning" variant="subtle" size="xs">
            <UIcon name="i-lucide-triangle-alert" class="w-3 h-3 mr-0.5" />
            {{ suspect.pct_change }}% change
          </UBadge>
          <span class="text-amber-500 text-[10px]">Verify against original document</span>
        </div>
      </div>
    </div>

    <!-- Safety Alerts -->
    <div v-if="allAlerts.length" class="rounded-xl border border-red-200 bg-red-50 p-4">
      <div class="flex items-center gap-2 mb-2">
        <UIcon name="i-lucide-octagon-alert" class="text-red-600 w-5 h-5" />
        <span class="text-sm font-semibold text-red-900">{{ $t('labs.safetyAlerts') }}</span>
      </div>
      <div class="space-y-1.5">
        <div v-for="(alert, i) in allAlerts" :key="i" class="text-xs text-red-700 flex items-center gap-2">
          <span class="text-red-400 font-mono">{{ alert.date }}</span>
          <NuxtLink :to="`/dictionary?q=${alert.param}`" class="font-semibold hover:text-red-900 underline decoration-dotted">{{ alert.param }}</NuxtLink>
          <span class="font-mono tabular-nums">= {{ Number(alert.value).toLocaleString('en-US', { maximumFractionDigits: 1 }) }}</span>
          <span class="text-red-400">(min: {{ Number(alert.threshold).toLocaleString('en-US', { maximumFractionDigits: 0 }) }})</span>
          <UBadge color="error" variant="subtle" size="xs">
            <UIcon name="i-lucide-octagon-alert" class="w-3 h-3 mr-0.5" />
            {{ actionLabel(alert.action) }}
          </UBadge>
        </div>
      </div>
    </div>

    <!-- Entry Form -->
    <div v-if="showForm" class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('labs.enterResults') }}</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div>
          <label class="text-xs text-gray-500 block mb-1">{{ $t('common.date') }}</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
          />
        </div>
        <div v-for="param in allLabParams" :key="param.key">
          <label class="text-xs text-gray-500 block mb-1">{{ param.label }} <span v-if="param.unit" class="text-gray-400">({{ param.unit }})</span></label>
          <input
            v-model.number="form.values[param.key]"
            type="number"
            step="any"
            :placeholder="refRangeText(param.key) || param.label"
            class="w-full rounded-lg border bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 tabular-nums"
            :class="formValueStatus(param.key)"
          />
        </div>
      </div>
      <div class="mb-4">
        <label class="text-xs text-gray-500 block mb-1">{{ $t('common.notes') }}</label>
        <input
          v-model="form.notes"
          type="text"
          :placeholder="$t('labs.placeholderNotes')"
          class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
        />
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitLab">{{ $t('common.save') }}</UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('error:') ? 'text-red-600' : 'text-green-600'">
          {{ submitMsg.startsWith('error:') ? $t('common.errorPrefix', { msg: submitMsg.slice(6) }) : $t('common.saved') }}
        </span>
      </div>
    </div>

    <!-- Charts — grouped by category -->
    <ClientOnly>
      <div v-for="cat in visibleCategories" :key="cat.id" class="space-y-3">
        <div class="flex items-center gap-2 pt-2">
          <UIcon :name="cat.icon" :class="cat.color" class="w-4 h-4" />
          <h2 class="text-xs font-semibold uppercase tracking-wider" :class="cat.color">{{ cat.label }}</h2>
          <div class="flex-1 border-b border-gray-100" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <LabChart
            v-for="param in cat.params.filter(p => hasData(p.key))"
            :key="param.key"
            :title="param.label"
            :labels="chartLabels"
            :values="getValues(param.key)"
            :threshold-min="param.thresholdKey ? getThreshold(param.thresholdKey) : undefined"
            :threshold-label="param.thresholdKey ? t('common.minSafe', { param: param.thresholdKey }) : undefined"
            :reference-min="labs?.reference_ranges?.[param.key]?.min"
            :reference-max="labs?.reference_ranges?.[param.key]?.max"
            :color="param.color"
            :unit="param.unit"
            :health-direction="param.healthDirection"
          />
        </div>
      </div>
      <div v-if="!labParams.some(p => hasData(p.key)) && !labs?.entries?.length" class="text-gray-400 text-center py-16 text-sm">
        {{ $t('labs.noData') }}
      </div>
    </ClientOnly>

    <!-- Data Table — with category headers -->
    <div v-if="labs?.entries?.length" class="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <span class="text-sm font-semibold text-gray-900">{{ $t('labs.resultsTable') }}</span>
        <div class="flex items-center gap-3 text-[10px] text-gray-400">
          <span class="inline-flex items-center gap-1"><UIcon name="i-lucide-circle-check" class="text-green-600 w-3 h-3" /> Normal</span>
          <span class="inline-flex items-center gap-1"><UIcon name="i-lucide-triangle-alert" class="text-amber-600 w-3 h-3" /> Out of range</span>
          <span class="inline-flex items-center gap-1"><UIcon name="i-lucide-octagon-alert" class="text-red-600 w-3 h-3" /> Critical</span>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-200">
              <th class="px-4 py-2 sticky left-0 bg-white z-10">
                <div class="text-gray-700">{{ $t('labs.sampleDate') }}</div>
              </th>
              <template v-for="cat in visibleCategories" :key="cat.id">
                <!-- Category separator -->
                <th
                  v-for="(p, pi) in cat.params"
                  :key="p.key"
                  class="px-3 py-2"
                  :class="pi === 0 ? 'border-l border-gray-200' : ''"
                >
                  <NuxtLink
                    :to="`/dictionary?q=${p.label}`"
                    class="hover:text-teal-700 underline decoration-dotted transition-colors text-gray-600"
                    :title="`Look up ${p.label} in dictionary`"
                  >
                    {{ p.label }}
                  </NuxtLink>
                  <div v-if="refRangeText(p.key)" class="text-[10px] text-gray-400 font-normal tabular-nums">{{ refRangeText(p.key) }}</div>
                </th>
              </template>
              <th class="px-3 py-2 border-l border-gray-200">{{ $t('common.notes') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr
              v-for="entry in sortedEntries"
              :key="entry.id"
              class="text-gray-700 cursor-pointer hover:bg-gray-50/80 transition-colors"
              @click="drilldown.open({ type: 'treatment_event', id: entry.id, label: `Labs ${entry.date}` })"
            >
              <td class="px-4 py-2.5 font-mono text-gray-900 sticky left-0 bg-white z-10">
                <div class="text-sm tabular-nums">{{ formatDate(entry.date) }}</div>
                <div v-if="entry.sync_date" class="text-[10px] text-gray-400" :title="$t('labs.syncDate')">
                  {{ $t('labs.syncDate') }}: {{ formatDate(entry.sync_date) }}
                </div>
              </td>
              <template v-for="cat in visibleCategories" :key="cat.id">
                <td
                  v-for="(p, pi) in cat.params"
                  :key="p.key"
                  class="px-3 py-2.5"
                  :class="[cellBgColor(entry, p.key), pi === 0 ? 'border-l border-gray-100' : '']"
                >
                  <div
                    v-if="entry.values?.[p.key] != null"
                    class="inline-flex items-center gap-1"
                  >
                    <!-- WCAG status icon -->
                    <UIcon
                      v-if="statusIcon(entry, p.key)"
                      :name="statusIcon(entry, p.key)"
                      :class="statusIconColor(entry, p.key)"
                      class="w-3 h-3 flex-shrink-0"
                    />
                    <!-- Value -->
                    <span
                      class="tabular-nums"
                      :class="entry.alerts?.some((a: any) => a.param === p.key) ? 'text-red-700 font-bold' : entry.value_statuses?.[p.key] === 'low' || entry.value_statuses?.[p.key] === 'high' ? 'text-amber-700 font-semibold' : 'text-gray-900'"
                    >
                      {{ typeof entry.values[p.key] === 'number' ? entry.values[p.key].toLocaleString() : String(entry.values[p.key]) }}
                    </span>
                    <!-- Direction arrow -->
                    <span
                      v-if="directionArrow(entry, p.key)"
                      class="text-[10px] font-bold"
                      :class="directionColor(entry, p.key)"
                      :title="entry.health_directions?.[p.key] === 'improving' ? t('labs.improving') : entry.health_directions?.[p.key] === 'worsening' ? t('labs.worsening') : t('labs.stable')"
                    >{{ directionArrow(entry, p.key) }}</span>
                    <!-- Suspect badge -->
                    <span
                      v-if="isSuspect(entry, p.key)"
                      class="ml-0.5 text-[9px] font-semibold text-amber-700 bg-amber-100 rounded px-1 py-0.5 whitespace-nowrap"
                      :title="`${isSuspect(entry, p.key).pct_change}% change from ${isSuspect(entry, p.key).prev_date}`"
                    >
                      ⚠ {{ isSuspect(entry, p.key).pct_change }}%
                    </span>
                  </div>
                  <span v-else class="text-gray-300">—</span>
                </td>
              </template>
              <td class="px-3 py-2.5 text-gray-400 border-l border-gray-100 max-w-[200px] truncate">{{ entry.notes || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
