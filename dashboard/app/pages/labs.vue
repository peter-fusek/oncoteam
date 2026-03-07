<script setup lang="ts">
const { fetchApi, apiUrl } = useOncoteamApi()

const { data: labs, refresh } = await fetchApi<{
  entries: Array<{
    id: number
    date: string
    values: Record<string, number>
    notes: string
    alerts: Array<{ param: string; value: number; threshold: number; action: string }>
  }>
  total: number
}>('/labs')

const { data: protocol } = await fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; action: string }>
}>('/protocol')

// Lab parameters to chart
const labParams = [
  { key: 'CEA', label: 'CEA', color: '#f59e0b', unit: 'ng/mL' },
  { key: 'CA_19_9', label: 'CA 19-9', color: '#8b5cf6', unit: 'U/mL' },
  { key: 'ANC', label: 'ANC', color: '#14b8a6', unit: '/uL', thresholdKey: 'ANC' },
  { key: 'PLT', label: 'Platelets', color: '#3b82f6', unit: '/uL', thresholdKey: 'PLT' },
  { key: 'creatinine', label: 'Creatinine', color: '#ef4444', unit: 'mg/dL' },
  { key: 'ALT', label: 'ALT', color: '#f97316', unit: 'U/L' },
  { key: 'AST', label: 'AST', color: '#ec4899', unit: 'U/L' },
  { key: 'hemoglobin', label: 'Hemoglobin', color: '#e11d48', unit: 'g/dL' },
]

const sortedEntries = computed(() => {
  if (!labs.value?.entries) return []
  return [...labs.value.entries].sort((a, b) => a.date.localeCompare(b.date))
})

const chartLabels = computed(() => sortedEntries.value.map(e => e.date))

function getValues(key: string): (number | null)[] {
  return sortedEntries.value.map(e => e.values?.[key] ?? null)
}

function getThreshold(key: string): number | undefined {
  return protocol.value?.lab_thresholds?.[key]?.min
}

function hasData(key: string): boolean {
  return sortedEntries.value.some(e => e.values?.[key] != null)
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
    await $fetch(apiUrl('/labs'), {
      method: 'POST',
      body: { date: form.date, values: cleanValues, notes: form.notes },
    })
    submitMsg.value = 'Saved'
    showForm.value = false
    form.values = {}
    form.notes = ''
    form.date = new Date().toISOString().slice(0, 10)
    await refresh()
  } catch (e: any) {
    submitMsg.value = `Error: ${e.message || e}`
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Lab Trends</h1>
        <p class="text-sm text-gray-400">{{ labs?.total ?? 0 }} lab result sets</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          :icon="showForm ? 'i-lucide-x' : 'i-lucide-plus'"
          :variant="showForm ? 'outline' : 'solid'"
          size="xs"
          :color="showForm ? 'neutral' : 'primary'"
          @click="showForm = !showForm"
        >
          {{ showForm ? 'Cancel' : 'Add Labs' }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <!-- Alerts Banner -->
    <div v-if="allAlerts.length" class="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
      <div class="flex items-center gap-2 mb-2">
        <UIcon name="i-lucide-triangle-alert" class="text-red-500" />
        <span class="text-sm font-semibold text-white">Safety Alerts</span>
      </div>
      <div class="space-y-1">
        <div v-for="(alert, i) in allAlerts" :key="i" class="text-xs text-red-400 flex items-center gap-2">
          <span class="text-gray-500">{{ alert.date }}</span>
          <span class="font-mono">{{ alert.param }}</span>
          <span>= {{ alert.value.toLocaleString() }}</span>
          <span class="text-gray-600">(min: {{ alert.threshold.toLocaleString() }})</span>
          <UBadge color="error" variant="subtle" size="xs">{{ alert.action }}</UBadge>
        </div>
      </div>
    </div>

    <!-- Entry Form -->
    <div v-if="showForm" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 class="text-sm font-semibold text-white mb-4">Enter Lab Results</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">Date</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          />
        </div>
        <div v-for="param in labParams" :key="param.key">
          <label class="text-xs text-gray-400 block mb-1">{{ param.label }} ({{ param.unit }})</label>
          <input
            v-model.number="form.values[param.key]"
            type="number"
            step="any"
            :placeholder="param.label"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          />
        </div>
      </div>
      <div class="mb-4">
        <label class="text-xs text-gray-400 block mb-1">Notes</label>
        <input
          v-model="form.notes"
          type="text"
          placeholder="Optional notes"
          class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
        />
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitLab">Save</UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('Error') ? 'text-red-500' : 'text-green-500'">
          {{ submitMsg }}
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
          :threshold-label="param.thresholdKey ? `Min safe (${param.thresholdKey})` : undefined"
          :color="param.color"
          :unit="param.unit"
        />
      </div>
      <div v-if="!labParams.some(p => hasData(p.key))" class="text-gray-600 text-center py-16 text-sm">
        No lab data yet — click "Add Labs" to enter results
      </div>
    </ClientOnly>

    <!-- Raw Data Table -->
    <div v-if="labs?.entries?.length" class="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div class="px-4 py-3 border-b border-gray-800">
        <span class="text-sm font-semibold text-white">Lab Results Table</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-left text-gray-500 border-b border-gray-800">
              <th class="px-4 py-2">Date</th>
              <th v-for="p in labParams" :key="p.key" class="px-3 py-2">{{ p.label }}</th>
              <th class="px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr
              v-for="entry in labs.entries"
              :key="entry.id"
              class="text-gray-300 cursor-pointer hover:bg-gray-800/30 transition-colors"
              @click="drilldown.open({ type: 'treatment_event', id: entry.id, label: `Labs ${entry.date}` })"
            >
              <td class="px-4 py-2 font-mono text-white">{{ entry.date }}</td>
              <td v-for="p in labParams" :key="p.key" class="px-3 py-2">
                <span
                  v-if="entry.values?.[p.key] != null"
                  :class="entry.alerts?.some((a: any) => a.param === p.key) ? 'text-red-400 font-semibold' : ''"
                >
                  {{ typeof entry.values[p.key] === 'number' ? entry.values[p.key].toLocaleString() : entry.values[p.key] }}
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
