<script setup lang="ts">
const { fetchApi, apiUrl } = useOncoteamApi()

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
        <h1 class="text-2xl font-bold text-white">Medications</h1>
        <p class="text-sm text-gray-400">Active medications and adherence tracking</p>
      </div>
      <div class="flex gap-2">
        <UButton icon="i-lucide-plus" size="xs" color="primary" @click="showForm = !showForm">
          Add
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="meds?.error" />

    <!-- Default Medications (regimen) -->
    <div v-if="meds?.default_medications?.length">
      <h2 class="text-sm font-semibold text-white mb-3">Active Regimen</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div
          v-for="med in meds.default_medications"
          :key="med.name"
          class="rounded-xl border border-gray-800 bg-gray-900/50 p-4"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm font-medium text-white">{{ med.name }}</span>
            <UBadge variant="subtle" size="xs" color="success">Active</UBadge>
          </div>
          <div class="text-xs text-gray-400 space-y-0.5">
            <div><span class="text-gray-500">Dose:</span> {{ med.dose }}</div>
            <div><span class="text-gray-500">Frequency:</span> {{ med.frequency }}</div>
            <div v-if="med.notes" class="text-gray-500 mt-1">{{ med.notes }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Medication Form -->
    <div v-if="showForm" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 class="text-sm font-semibold text-white mb-4">New Medication Entry</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="text-xs text-gray-400 block mb-1">Date</label>
          <input
            v-model="form.date"
            type="date"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">Medication Name *</label>
          <input
            v-model="form.name"
            type="text"
            placeholder="e.g. Clexane"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">Dose</label>
          <input
            v-model="form.dose"
            type="text"
            placeholder="e.g. 0.6ml SC"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">Frequency</label>
          <select
            v-model="form.frequency"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          >
            <option value="">-</option>
            <option value="1x/day">1x/day</option>
            <option value="2x/day">2x/day</option>
            <option value="3x/day">3x/day</option>
            <option value="as needed">As needed</option>
            <option value="with chemo">With chemo</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">Time of Day</label>
          <select
            v-model="form.time_of_day"
            class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500"
          >
            <option value="">-</option>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
            <option value="evening">Evening</option>
            <option value="bedtime">Bedtime</option>
          </select>
        </div>
      </div>
      <div class="mb-4">
        <label class="text-xs text-gray-400 block mb-1">Notes</label>
        <textarea
          v-model="form.notes"
          rows="2"
          placeholder="Additional notes..."
          class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
        />
      </div>
      <div class="flex items-center gap-3">
        <UButton :loading="submitting" color="primary" size="sm" @click="submitMed">
          Save
        </UButton>
        <UButton variant="ghost" size="sm" color="neutral" @click="showForm = false">
          Cancel
        </UButton>
        <span v-if="submitMsg" class="text-xs" :class="submitMsg.startsWith('Error') ? 'text-red-500' : 'text-green-500'">
          {{ submitMsg }}
        </span>
      </div>
    </div>

    <!-- Medication History -->
    <div v-if="meds?.medications?.length" class="space-y-2">
      <h2 class="text-sm font-semibold text-white">History</h2>
      <div
        v-for="med in meds.medications"
        :key="med.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="drilldown.open({ type: 'medication', id: med.id, label: `${med.name} ${med.date}` })"
      >
        <div class="flex items-center justify-between mb-1">
          <span class="text-sm font-medium text-white">{{ med.name }}</span>
          <span class="text-xs text-gray-500">{{ med.date }}</span>
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
      No medication entries yet — use the Add button above
    </div>
  </div>
</template>
