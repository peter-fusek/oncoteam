<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
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
  }>
  reference_ranges: Record<string, { min: number; max: number; unit: string; note?: string }>
  total: number
  error?: string
}>('/labs', { lazy: true })

const { data: protocol } = fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; action: string }>
}>('/protocol', { lazy: true })

// Rookie/Pro mode
const proMode = ref(false)

// Lab parameters — rookie shows essential only, pro shows all
const rookieKeys = new Set(['CEA', 'CA_19_9', 'ANC', 'PLT', 'WBC', 'hemoglobin'])

const allLabParams = [
  { key: 'CEA', label: 'CEA', color: '#f59e0b', unit: 'ng/mL' },
  { key: 'CA_19_9', label: 'CA 19-9', color: '#8b5cf6', unit: 'U/mL' },
  { key: 'ANC', label: 'ANC', color: '#14b8a6', unit: '/uL', thresholdKey: 'ANC' },
  { key: 'PLT', label: 'Platelets', color: '#3b82f6', unit: '/uL', thresholdKey: 'PLT' },
  { key: 'WBC', label: 'WBC', color: '#06b6d4', unit: '×10³/µL' },
  { key: 'hemoglobin', label: 'Hemoglobin', color: '#e11d48', unit: 'g/dL' },
  { key: 'ABS_LYMPH', label: 'Lymphocytes', color: '#a855f7', unit: '/µL' },
  { key: 'creatinine', label: 'Creatinine', color: '#ef4444', unit: 'mg/dL' },
  { key: 'bilirubin', label: 'Bilirubin', color: '#eab308', unit: 'mg/dL' },
  { key: 'ALT', label: 'ALT', color: '#f97316', unit: 'U/L' },
  { key: 'AST', label: 'AST', color: '#ec4899', unit: 'U/L' },
  { key: 'SII', label: 'SII', color: '#64748b', unit: '' },
  { key: 'NE_LY_RATIO', label: 'Ne/Ly', color: '#78716c', unit: '' },
]

const labParams = computed(() => {
  if (proMode.value) return allLabParams
  return allLabParams.filter(p => rookieKeys.has(p.key))
})

const sortedEntries = computed(() => {
  if (!labs.value?.entries) return []
  return [...labs.value.entries].sort((a, b) => b.date.localeCompare(a.date))
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
  if (health === 'improving') return 'text-green-400'
  if (health === 'worsening') return 'text-red-400'
  return 'text-gray-500'
}

function cellBgColor(entry: any, key: string): string {
  if (entry.alerts?.some((a: any) => a.param === key)) return 'bg-red-500/10'
  const status = entry.value_statuses?.[key]
  if (status === 'low' || status === 'high') return 'bg-amber-500/5'
  if (status === 'normal' && entry.values?.[key] != null) return 'bg-green-500/5'
  return ''
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

function statusColor(status?: string): string {
  if (status === 'low') return 'text-amber-400 font-semibold'
  if (status === 'high') return 'text-amber-400 font-semibold'
  return ''
}

function refRangeText(key: string): string {
  const ref = labs.value?.reference_ranges?.[key]
  if (!ref) return ''
  return `${ref.min.toLocaleString()}–${ref.max.toLocaleString()}`
}

function formValueStatus(key: string): string {
  const val = form.values[key]
  if (val == null || val === '') return 'border-gray-700'
  const ref = labs.value?.reference_ranges?.[key]
  if (!ref) return 'border-gray-700'
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
}
function actionLabel(action: string): string {
  return ACTION_LABELS[action] || action.replace(/_/g, ' ')
}

// All alerts across entries
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
    await $fetch('/api/oncoteam/labs', {
      method: 'POST',
      body: { date: form.date, values: cleanValues, notes: form.notes },
    })
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
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('labs.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('labs.subtitle', { count: labs?.total ?? 0 }) }}</p>
        <LastUpdated :timestamp="labs?.last_updated" />
      </div>
      <div class="flex items-center gap-2">
        <!-- Rookie/Pro toggle -->
        <div class="flex rounded-lg border border-gray-700 overflow-hidden">
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="!proMode ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
            @click="proMode = false"
          >
            {{ $t('labs.rookie') }}
          </button>
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="proMode ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
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

    <!-- Alerts Banner -->
    <div v-if="allAlerts.length" class="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
      <div class="flex items-center gap-2 mb-2">
        <UIcon name="i-lucide-triangle-alert" class="text-red-500" />
        <span class="text-sm font-semibold text-white">{{ $t('labs.safetyAlerts') }}</span>
      </div>
      <div class="space-y-1">
        <div v-for="(alert, i) in allAlerts" :key="i" class="text-xs text-red-400 flex items-center gap-2">
          <span class="text-gray-500">{{ alert.date }}</span>
          <NuxtLink :to="`/dictionary?q=${alert.param}`" class="font-mono hover:text-red-300 underline decoration-dotted">{{ alert.param }}</NuxtLink>
          <span>= {{ Number(alert.value).toLocaleString('en-US', { maximumFractionDigits: 1 }) }}</span>
          <span class="text-gray-600">(min: {{ Number(alert.threshold).toLocaleString('en-US', { maximumFractionDigits: 0 }) }})</span>
          <UBadge color="error" variant="subtle" size="xs">{{ actionLabel(alert.action) }}</UBadge>
        </div>
      </div>
    </div>

    <!-- Entry Form -->
    <div v-if="showForm" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 class="text-sm font-semibold text-white mb-4">{{ $t('labs.enterResults') }}</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('common.date') }}</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          />
        </div>
        <div v-for="param in allLabParams" :key="param.key">
          <label class="text-xs text-gray-400 block mb-1">{{ param.label }} <span v-if="param.unit" class="text-gray-600">({{ param.unit }})</span></label>
          <input
            v-model.number="form.values[param.key]"
            type="number"
            step="any"
            :placeholder="refRangeText(param.key) || param.label"
            class="w-full rounded-lg border bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
            :class="formValueStatus(param.key)"
          />
        </div>
      </div>
      <div class="mb-4">
        <label class="text-xs text-gray-400 block mb-1">{{ $t('common.notes') }}</label>
        <input
          v-model="form.notes"
          type="text"
          :placeholder="$t('labs.placeholderNotes')"
          class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
        />
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitLab">{{ $t('common.save') }}</UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('error:') ? 'text-red-500' : 'text-green-500'">
          {{ submitMsg.startsWith('error:') ? $t('common.errorPrefix', { msg: submitMsg.slice(6) }) : $t('common.saved') }}
        </span>
      </div>
    </div>

    <!-- Charts -->
    <ClientOnly>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <LabChart
          v-for="param in labParams.filter(p => hasData(p.key))"
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
        />
      </div>
      <div v-if="!labParams.some(p => hasData(p.key)) && !labs?.entries?.length" class="text-gray-600 text-center py-16 text-sm">
        {{ $t('labs.noData') }}
      </div>
    </ClientOnly>

    <!-- Raw Data Table -->
    <div v-if="labs?.entries?.length" class="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div class="px-4 py-3 border-b border-gray-800">
        <span class="text-sm font-semibold text-white">{{ $t('labs.resultsTable') }}</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-800">
              <th class="px-4 py-2">
                <div>{{ $t('labs.sampleDate') }}</div>
              </th>
              <th v-for="p in labParams" :key="p.key" class="px-3 py-2">
                <NuxtLink :to="`/dictionary?q=${p.label}`" class="hover:text-teal-400 underline decoration-dotted transition-colors" :title="`Look up ${p.label} in dictionary`">{{ p.label }}</NuxtLink>
                <div v-if="refRangeText(p.key)" class="text-[10px] text-gray-600 font-normal">{{ refRangeText(p.key) }}</div>
              </th>
              <th class="px-3 py-2">{{ $t('common.notes') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr
              v-for="entry in sortedEntries"
              :key="entry.id"
              class="text-gray-300 cursor-pointer hover:bg-gray-800/30 transition-colors"
              @click="drilldown.open({ type: 'treatment_event', id: entry.id, label: `Labs ${entry.date}` })"
            >
              <td class="px-4 py-2 font-mono text-white">
                <div>{{ formatDate(entry.date) }}</div>
                <div v-if="entry.sync_date" class="text-[10px] text-gray-600" :title="$t('labs.syncDate')">
                  {{ $t('labs.syncDate') }}: {{ formatDate(entry.sync_date) }}
                </div>
              </td>
              <td
                v-for="p in labParams"
                :key="p.key"
                class="px-3 py-2"
                :class="cellBgColor(entry, p.key)"
              >
                <span
                  v-if="entry.values?.[p.key] != null"
                  class="inline-flex items-center gap-0.5"
                >
                  <span
                    :class="entry.alerts?.some((a: any) => a.param === p.key) ? 'text-red-400 font-semibold' : statusColor(entry.value_statuses?.[p.key])"
                    :title="entry.value_statuses?.[p.key] === 'low' ? t('labs.belowRange') : entry.value_statuses?.[p.key] === 'high' ? t('labs.aboveRange') : ''"
                  >
                    {{ typeof entry.values[p.key] === 'number' ? entry.values[p.key].toLocaleString() : entry.values[p.key] }}
                  </span>
                  <span
                    v-if="directionArrow(entry, p.key)"
                    class="text-[10px]"
                    :class="directionColor(entry, p.key)"
                    :title="entry.health_directions?.[p.key] === 'improving' ? t('labs.improving') : entry.health_directions?.[p.key] === 'worsening' ? t('labs.worsening') : t('labs.stable')"
                  >{{ directionArrow(entry, p.key) }}</span>
                </span>
                <span v-else class="text-gray-700">-</span>
              </td>
              <td class="px-3 py-2 text-gray-500">{{ entry.notes || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
