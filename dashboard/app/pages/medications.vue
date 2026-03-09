<script setup lang="ts">
const { fetchApi, apiUrl } = useOncoteamApi()
const { t } = useI18n()
const { formatDate, formatDateShort } = useFormatDate()

const { data: meds, refresh } = await fetchApi<{
  medications: Array<{
    id: number
    date: string
    name: string
    dose: string | null
    frequency: string | null
    time_of_day: string | null
    active: boolean
    notes: string | null
  }>
  default_medications: Array<{
    name: string
    dose: string
    frequency: string
    active: boolean
    notes: string
  }>
  adherence: {
    last_7_days: Array<{ date: string; medications: Record<string, boolean> }>
    compliance_pct: number | null
    missed: Array<{ date: string; medication: string }>
  }
  total: number
  error?: string
}>('/medications')

const showForm = ref(false)
const form = reactive({
  date: new Date().toISOString().slice(0, 10),
  name: '',
  dose: '',
  frequency: '',
  time_of_day: '',
  notes: '',
})

// Adherence check-in
const checkin = reactive<Record<string, boolean>>({})
const checkinSubmitting = ref(false)
const checkinMsg = ref('')

// Initialize check-in toggles from default medications
watchEffect(() => {
  if (meds.value?.default_medications) {
    for (const med of meds.value.default_medications) {
      if (!(med.name in checkin)) {
        checkin[med.name] = false
      }
    }
  }
})

async function submitCheckin() {
  checkinSubmitting.value = true
  checkinMsg.value = ''
  try {
    await $fetch(apiUrl('/medications'), {
      method: 'POST',
      body: {
        date: new Date().toISOString().slice(0, 10),
        medications: { ...checkin },
      },
    })
    checkinMsg.value = 'Saved'
    await refresh()
  } catch (e: any) {
    checkinMsg.value = `Error: ${e.message || e}`
  } finally {
    checkinSubmitting.value = false
  }
}

const submitting = ref(false)
const submitMsg = ref('')

async function submitMed() {
  submitting.value = true
  submitMsg.value = ''
  try {
    await $fetch(apiUrl('/medications'), {
      method: 'POST',
      body: form,
    })
    submitMsg.value = 'Saved'
    form.name = ''
    form.dose = ''
    form.frequency = ''
    form.time_of_day = ''
    form.notes = ''
    form.date = new Date().toISOString().slice(0, 10)
    showForm.value = false
    await refresh()
  } catch (e: any) {
    submitMsg.value = `Error: ${e.message || e}`
  } finally {
    submitting.value = false
  }
}

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('medications.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('medications.subtitle') }}</p>
      </div>
      <div class="flex gap-2">
        <UButton icon="i-lucide-plus" size="xs" color="primary" @click="showForm = !showForm">
          {{ $t('common.add') }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="meds?.error" />

    <!-- Today's Check-in -->
    <div class="rounded-xl border border-teal-500/20 bg-teal-500/5 p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-white">{{ $t('medications.todayCheckin') }}</h2>
        <UBadge v-if="meds?.adherence?.compliance_pct != null" variant="subtle" size="xs" :color="meds.adherence.compliance_pct >= 90 ? 'success' : meds.adherence.compliance_pct >= 70 ? 'warning' : 'error'">
          {{ $t('medications.compliance', { pct: meds.adherence.compliance_pct }) }}
        </UBadge>
      </div>
      <div class="flex flex-wrap gap-3 mb-3">
        <button
          v-for="med in meds?.default_medications"
          :key="med.name"
          class="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-all"
          :class="checkin[med.name] ? 'bg-teal-500/20 border-teal-500 text-teal-300' : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600'"
          @click="checkin[med.name] = !checkin[med.name]"
        >
          <UIcon :name="checkin[med.name] ? 'i-lucide-check-circle' : 'i-lucide-circle'" />
          {{ med.name }}
        </button>
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="checkinSubmitting" color="primary" size="xs" @click="submitCheckin">{{ $t('medications.logToday') }}</UButton>
        <span v-if="checkinMsg" class="text-xs" :class="checkinMsg.startsWith('Error') ? 'text-red-500' : 'text-green-500'">{{ checkinMsg }}</span>
      </div>
    </div>

    <!-- 7-Day Adherence Grid -->
    <div v-if="meds?.adherence?.last_7_days?.length" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <h2 class="text-xs font-semibold text-gray-400 mb-3">{{ $t('medications.adherence7Day') }}</h2>
      <div class="overflow-x-auto">
        <div class="flex gap-2">
          <div
            v-for="day in meds.adherence.last_7_days"
            :key="day.date"
            class="flex flex-col items-center gap-1 min-w-[60px]"
          >
            <span class="text-[10px] text-gray-500">{{ formatDateShort(day.date) }}</span>
            <div
              v-for="(taken, medName) in day.medications"
              :key="medName"
              class="w-5 h-5 rounded-sm flex items-center justify-center text-[10px]"
              :class="taken ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'"
              :title="`${medName}: ${taken ? t('medications.taken') : t('medications.missed')}`"
            >
              {{ taken ? '✓' : '✗' }}
            </div>
          </div>
        </div>
        <div class="flex gap-1 mt-2">
          <div v-for="med in meds.default_medications" :key="med.name" class="text-[10px] text-gray-600">
            {{ med.name }}
          </div>
        </div>
      </div>
      <div v-if="meds.adherence.missed?.length" class="mt-2 text-xs text-red-400">
        {{ $t('medications.missed') }}: {{ meds.adherence.missed.map(m => `${m.medication} (${formatDateShort(m.date)})`).join(', ') }}
      </div>
    </div>

    <!-- Default Medications (regimen) -->
    <div v-if="meds?.default_medications?.length">
      <h2 class="text-sm font-semibold text-white mb-3">{{ $t('medications.activeRegimen') }}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div
          v-for="med in meds.default_medications"
          :key="med.name"
          class="rounded-xl border border-gray-800 bg-gray-900/50 p-4"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm font-medium text-white">{{ med.name }}</span>
            <UBadge variant="subtle" size="xs" color="success">{{ $t('common.active') }}</UBadge>
          </div>
          <div class="text-xs text-gray-400 space-y-0.5">
            <div><span class="text-gray-500">{{ $t('medications.dose') }}:</span> {{ med.dose }}</div>
            <div><span class="text-gray-500">{{ $t('medications.frequency') }}:</span> {{ med.frequency }}</div>
            <div v-if="med.notes" class="text-gray-500 mt-1">{{ med.notes }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Medication Form -->
    <div v-if="showForm" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 class="text-sm font-semibold text-white mb-4">{{ $t('medications.newMedEntry') }}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('common.date') }}</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('medications.medName') }} *</label>
          <input
            v-model="form.name"
            type="text"
            :placeholder="$t('medications.medName')"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('medications.dose') }}</label>
          <input
            v-model="form.dose"
            type="text"
            :placeholder="$t('medications.dose')"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('medications.frequency') }}</label>
          <select
            v-model="form.frequency"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          >
            <option value="">-</option>
            <option value="1x/day">{{ $t('medications.frequencies.1xDay') }}</option>
            <option value="2x/day">{{ $t('medications.frequencies.2xDay') }}</option>
            <option value="3x/day">{{ $t('medications.frequencies.3xDay') }}</option>
            <option value="as needed">{{ $t('medications.frequencies.asNeeded') }}</option>
            <option value="with chemo">{{ $t('medications.frequencies.withChemo') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">{{ $t('medications.timeOfDay') }}</label>
          <select
            v-model="form.time_of_day"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          >
            <option value="">-</option>
            <option value="morning">{{ $t('medications.times.morning') }}</option>
            <option value="afternoon">{{ $t('medications.times.afternoon') }}</option>
            <option value="evening">{{ $t('medications.times.evening') }}</option>
            <option value="bedtime">{{ $t('medications.times.bedtime') }}</option>
          </select>
        </div>
      </div>
      <div class="mb-4">
        <label class="text-xs text-gray-400 block mb-1">{{ $t('common.notes') }}</label>
        <textarea
          v-model="form.notes"
          rows="2"
          :placeholder="$t('common.notes')"
          class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
        />
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitMed">
          {{ $t('common.save') }}
        </UButton>
        <UButton variant="ghost" size="sm" color="neutral" @click="showForm = false">
          {{ $t('common.cancel') }}
        </UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('Error') ? 'text-red-500' : 'text-green-500'">
          {{ submitMsg }}
        </span>
      </div>
    </div>

    <!-- Medication History -->
    <div v-if="meds?.medications?.length" class="space-y-2">
      <h2 class="text-sm font-semibold text-white">{{ $t('common.history') }}</h2>
      <div
        v-for="med in meds.medications"
        :key="med.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="drilldown.open({ type: 'medication', id: med.id, label: `${med.name} ${med.date}` })"
      >
        <div class="flex items-center justify-between mb-1">
          <span class="text-sm font-medium text-white">{{ med.name }}</span>
          <span class="text-xs text-gray-500">{{ formatDate(med.date) }}</span>
        </div>
        <div class="text-xs text-gray-400">
          <span v-if="med.dose">{{ med.dose }}</span>
          <span v-if="med.frequency"> &middot; {{ med.frequency }}</span>
          <span v-if="med.time_of_day"> &middot; {{ med.time_of_day }}</span>
        </div>
        <p v-if="med.notes" class="text-xs text-gray-500 mt-1">{{ med.notes }}</p>
      </div>
    </div>

    <div v-else-if="!meds?.error" class="text-gray-600 text-center py-8 text-sm">
      {{ $t('medications.noEntries') }}
    </div>
  </div>
</template>
