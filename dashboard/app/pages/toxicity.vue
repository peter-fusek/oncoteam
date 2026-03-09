<script setup lang="ts">
const { fetchApi, apiUrl } = useOncoteamApi()
const { activeRole } = useUserRole()
const { t } = useI18n()
const { formatDate } = useFormatDate()

const { data: toxicity, refresh } = await fetchApi<{
  entries: Array<{
    id: number
    date: string
    notes: string
    metadata: Record<string, number>
  }>
  total: number
  error?: string
}>('/toxicity')

const { data: weightData } = await fetchApi<{
  entries: Array<{
    date: string
    weight_kg: number
    pct_change: number
    alert: boolean
  }>
  baseline_weight_kg: number
  alerts: Array<{ date: string; weight_kg: number; loss_pct: number; action: string; severity: string }>
  nutrition_escalation: Array<{ loss_pct: number; action: string; severity: string }>
  total: number
}>('/weight')

const grades = [0, 1, 2, 3, 4]
const gradeLabels = computed(() => {
  const prefix = activeRole.value === 'patient' ? 'toxicity.patientGrades' : 'toxicity.grades'
  return Object.fromEntries(grades.map(g => [g, t(`${prefix}.${g}`)]))
})
const gradeColors: Record<number, string> = {
  0: 'text-green-500',
  1: 'text-yellow-500',
  2: 'text-orange-500',
  3: 'text-red-500',
  4: 'text-red-700',
}

const form = reactive({
  date: new Date().toISOString().slice(0, 10),
  neuropathy: 0,
  diarrhea: 0,
  mucositis: 0,
  fatigue: 0,
  hand_foot: 0,
  nausea: 0,
  weight_kg: null as number | null,
  ecog: null as number | null,
  appetite: null as number | null,
  oral_intake: null as number | null,
  notes: '',
})

const submitting = ref(false)
const submitMsg = ref('')

async function submitLog() {
  submitting.value = true
  submitMsg.value = ''
  try {
    await $fetch(apiUrl('/toxicity'), {
      method: 'POST',
      body: form,
    })
    submitMsg.value = 'saved'
    // Reset form
    form.neuropathy = 0
    form.diarrhea = 0
    form.mucositis = 0
    form.fatigue = 0
    form.hand_foot = 0
    form.nausea = 0
    form.weight_kg = null
    form.ecog = null
    form.appetite = null
    form.oral_intake = null
    form.notes = ''
    form.date = new Date().toISOString().slice(0, 10)
    await refresh()
  } catch (e: any) {
    submitMsg.value = `error:${e.message || e}`
  } finally {
    submitting.value = false
  }
}

const toxicityFields = computed(() => [
  { key: 'neuropathy', label: t('toxicity.fields.neuropathy'), icon: 'i-lucide-hand' },
  { key: 'diarrhea', label: t('toxicity.fields.diarrhea'), icon: 'i-lucide-droplets' },
  { key: 'mucositis', label: t('toxicity.fields.mucositis'), icon: 'i-lucide-circle-dot' },
  { key: 'fatigue', label: t('toxicity.fields.fatigue'), icon: 'i-lucide-battery-low' },
  { key: 'hand_foot', label: t('toxicity.fields.handFoot'), icon: 'i-lucide-footprints' },
  { key: 'nausea', label: t('toxicity.fields.nausea'), icon: 'i-lucide-frown' },
])

const drilldown = useDrilldown()

function getMaxGrade(entry: { metadata: Record<string, number> }): number {
  return Math.max(
    ...[
      entry.metadata?.neuropathy ?? 0,
      entry.metadata?.diarrhea ?? 0,
      entry.metadata?.mucositis ?? 0,
      entry.metadata?.fatigue ?? 0,
      entry.metadata?.hand_foot ?? 0,
      entry.metadata?.nausea ?? 0,
    ]
  )
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('toxicity.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('toxicity.subtitle') }}</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <ApiErrorBanner :error="toxicity?.error" />

    <!-- Log Form -->
    <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 class="text-sm font-semibold text-white mb-4">{{ $t('toxicity.newEntry') }}</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('common.date') }}</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
      </div>

      <!-- Toxicity Grade Selectors -->
      <div class="space-y-3 mb-4">
        <div v-for="field in toxicityFields" :key="field.key" class="flex items-center gap-3">
          <div class="flex items-center gap-2 w-48 shrink-0">
            <UIcon :name="field.icon" class="text-gray-500" />
            <span class="text-sm text-gray-300">{{ field.label }}</span>
          </div>
          <div class="flex gap-1">
            <button
              v-for="g in grades"
              :key="g"
              class="w-8 h-8 rounded-lg text-xs font-medium transition-all border"
              :class="(form as any)[field.key] === g
                ? 'bg-gray-700 border-teal-500 text-white'
                : 'bg-gray-800/50 border-gray-700 text-gray-500 hover:border-gray-600'"
              @click="(form as any)[field.key] = g"
            >
              {{ g }}
            </button>
          </div>
          <span class="text-xs ml-2" :class="gradeColors[(form as any)[field.key]]">
            {{ gradeLabels[(form as any)[field.key]] }}
          </span>

        </div>
      </div>

      <!-- Weight, ECOG & Nutrition -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('toxicity.weight') }}</label>
          <input
            v-model.number="form.weight_kg"
            type="number"
            step="0.1"
            :placeholder="$t('toxicity.placeholderWeight')"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('toxicity.ecog') }}</label>
          <select
            v-model.number="form.ecog"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          >
            <option :value="null">-</option>
            <option :value="0">{{ $t('toxicity.ecogLevels.0') }}</option>
            <option :value="1">{{ $t('toxicity.ecogLevels.1') }}</option>
            <option :value="2">{{ $t('toxicity.ecogLevels.2') }}</option>
            <option :value="3">{{ $t('toxicity.ecogLevels.3') }}</option>
            <option :value="4">{{ $t('toxicity.ecogLevels.4') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('toxicity.appetite') }}</label>
          <div class="flex gap-1">
            <button
              v-for="g in grades"
              :key="g"
              class="w-8 h-8 rounded-lg text-xs font-medium transition-all border"
              :class="form.appetite === g
                ? 'bg-gray-700 border-teal-500 text-white'
                : 'bg-gray-800/50 border-gray-700 text-gray-500 hover:border-gray-600'"
              @click="form.appetite = g"
            >
              {{ g }}
            </button>
          </div>
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('toxicity.oralIntake') }}</label>
          <input
            v-model.number="form.oral_intake"
            type="number"
            min="0"
            max="100"
            step="10"
            :placeholder="$t('toxicity.placeholderOralIntake')"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
      </div>

      <!-- Notes -->
      <div class="mb-4">
        <label class="text-xs text-gray-400 block mb-1">{{ $t('common.notes') }}</label>
        <textarea
          v-model="form.notes"
          rows="2"
          :placeholder="$t('toxicity.placeholderNotes')"
          class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
        />
      </div>

      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitLog">
          {{ $t('toxicity.saveEntry') }}
        </UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('error:') ? 'text-red-500' : 'text-green-500'">
          {{ submitMsg.startsWith('error:') ? $t('common.errorPrefix', { msg: submitMsg.slice(6) }) : $t('common.saved') }}
        </span>
      </div>
    </div>

    <!-- History -->
    <div v-if="toxicity?.entries?.length" class="space-y-2">
      <h2 class="text-sm font-semibold text-white">{{ $t('common.history') }}</h2>
      <div
        v-for="entry in toxicity.entries"
        :key="entry.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="drilldown.open({ type: 'treatment_event', id: entry.id, label: `Toxicity ${entry.date}` })"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-white">{{ formatDate(entry.date) }}</span>
          <UBadge
            :color="getMaxGrade(entry) >= 3 ? 'error' : getMaxGrade(entry) >= 2 ? 'warning' : 'success'"
            variant="subtle"
            size="xs"
          >
            {{ $t('toxicity.maxGrade', { grade: getMaxGrade(entry) }) }}
          </UBadge>
        </div>
        <div class="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
          <div v-for="field in toxicityFields" :key="field.key">
            <span class="text-gray-500">{{ field.label.split(' ')[0] }}</span>
            <span class="ml-1 font-medium" :class="gradeColors[entry.metadata?.[field.key] ?? 0]">
              {{ entry.metadata?.[field.key] ?? 0 }}
            </span>
          </div>
        </div>
        <div v-if="entry.metadata?.weight_kg" class="text-xs text-gray-500 mt-1">
          {{ $t('toxicity.weight') }}: {{ entry.metadata.weight_kg }} kg
          <span v-if="entry.metadata?.ecog != null">&middot; {{ $t('toxicity.ecog') }}: {{ entry.metadata.ecog }}</span>
        </div>
        <p v-if="entry.notes" class="text-xs text-gray-400 mt-1">{{ entry.notes }}</p>
      </div>
    </div>

    <div v-else-if="!toxicity?.error" class="text-gray-600 text-center py-8 text-sm">
      {{ $t('toxicity.noEntries') }}
    </div>

    <!-- Weight Trend -->
    <div v-if="weightData?.entries?.length" class="space-y-2">
      <h2 class="text-sm font-semibold text-white">{{ $t('toxicity.weightTrend') }}</h2>

      <!-- Weight alert banner -->
      <div
        v-if="weightData.alerts?.length"
        class="rounded-lg border p-3"
        :class="weightData.alerts.some(a => a.severity === 'critical') ? 'border-red-500/30 bg-red-500/5' : 'border-amber-500/30 bg-amber-500/5'"
      >
        <div v-for="(alert, i) in weightData.alerts" :key="i" class="flex items-center gap-2 text-sm">
          <UIcon name="i-lucide-triangle-alert" :class="alert.severity === 'critical' ? 'text-red-500' : 'text-amber-500'" class="shrink-0" />
          <span :class="alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'">
            -{{ alert.loss_pct }}% — {{ alert.action }}
          </span>
        </div>
      </div>

      <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div v-for="entry in weightData.entries" :key="entry.date">
            <span class="text-gray-500">{{ formatDate(entry.date) }}</span>
            <span class="ml-2 font-medium" :class="entry.alert ? 'text-red-400' : 'text-white'">
              {{ entry.weight_kg }} kg
            </span>
            <span class="text-xs ml-1" :class="entry.pct_change < 0 ? 'text-amber-400' : 'text-green-400'">
              {{ entry.pct_change > 0 ? '+' : '' }}{{ entry.pct_change }}%
            </span>
          </div>
        </div>
        <div class="text-xs text-gray-500 mt-2">
          {{ $t('toxicity.baseline') }}: {{ weightData.baseline_weight_kg }} kg &middot; {{ $t('toxicity.alertThreshold') }}
        </div>
      </div>

      <!-- Nutrition Escalation Table -->
      <div v-if="weightData.nutrition_escalation?.length" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h3 class="text-xs font-semibold text-gray-400 mb-2">{{ $t('toxicity.nutritionEscalation') }}</h3>
        <div class="space-y-1">
          <div
            v-for="rule in weightData.nutrition_escalation"
            :key="rule.loss_pct"
            class="flex items-center gap-3 text-xs py-1"
          >
            <UBadge
              :color="rule.severity === 'critical' ? 'error' : 'warning'"
              variant="subtle"
              size="xs"
            >
              -{{ rule.loss_pct }}%
            </UBadge>
            <span class="text-gray-300">{{ rule.action }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
