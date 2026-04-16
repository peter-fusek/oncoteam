<script setup lang="ts">
const { t } = useI18n()
const { locale } = useI18n()
const { activePatientId } = useActivePatient()
const { state, generateAndDownload } = useExportPackage()

const sections = reactive({
  patient: true,
  labs: true,
  timeline: true,
  protocol: true,
})

const dateFrom = ref('')
const dateTo = ref('')
const format = ref<'json' | 'html'>('html')

const showDateRange = computed(() => sections.labs || sections.timeline)
const hasSelection = computed(
  () => sections.patient || sections.labs || sections.timeline || sections.protocol,
)

async function download() {
  await generateAndDownload({
    sections: { ...sections },
    dateFrom: dateFrom.value || undefined,
    dateTo: dateTo.value || undefined,
    format: format.value,
    patientId: activePatientId.value,
    lang: locale.value,
  })
}
</script>

<template>
  <div class="max-w-2xl mx-auto space-y-6">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 font-display">
        {{ t('export.title') }}
      </h1>
      <p class="text-sm text-gray-500 mt-1">
        {{ t('export.subtitle') }}
      </p>
    </div>

    <!-- Error banner -->
    <ApiErrorBanner v-if="state.error" :error="state.error" />

    <!-- Sections card -->
    <div class="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
      <h2 class="text-sm font-semibold text-gray-700">
        {{ t('export.sectionsTitle') }}
      </h2>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="sections.patient"
          type="checkbox"
          class="mt-0.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.patient') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.patientDesc') }}</p>
        </div>
      </label>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="sections.labs"
          type="checkbox"
          class="mt-0.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.labs') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.labsDesc') }}</p>
        </div>
      </label>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="sections.timeline"
          type="checkbox"
          class="mt-0.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.timeline') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.timelineDesc') }}</p>
        </div>
      </label>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="sections.protocol"
          type="checkbox"
          class="mt-0.5 rounded border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.protocol') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.protocolDesc') }}</p>
        </div>
      </label>
    </div>

    <!-- Date range card (conditional) -->
    <div v-if="showDateRange" class="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <h2 class="text-sm font-semibold text-gray-700">
        {{ t('export.dateRange') }}
      </h2>
      <p class="text-xs text-gray-500">{{ t('export.dateHint') }}</p>
      <div class="flex gap-4">
        <div class="flex-1">
          <label class="block text-xs font-medium text-gray-600 mb-1">{{ t('export.dateFrom') }}</label>
          <input
            v-model="dateFrom"
            type="date"
            class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
        <div class="flex-1">
          <label class="block text-xs font-medium text-gray-600 mb-1">{{ t('export.dateTo') }}</label>
          <input
            v-model="dateTo"
            type="date"
            class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30"
          />
        </div>
      </div>
    </div>

    <!-- Format card -->
    <div class="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <h2 class="text-sm font-semibold text-gray-700">
        {{ t('export.format') }}
      </h2>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="format"
          type="radio"
          value="html"
          class="mt-0.5 border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.formatHtml') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.formatHtmlDesc') }}</p>
        </div>
      </label>

      <label class="flex items-start gap-3 cursor-pointer">
        <input
          v-model="format"
          type="radio"
          value="json"
          class="mt-0.5 border-gray-300 text-teal-600 focus:ring-teal-500/30"
        />
        <div>
          <span class="text-sm font-medium text-gray-900">{{ t('export.formatJson') }}</span>
          <p class="text-xs text-gray-500">{{ t('export.formatJsonDesc') }}</p>
        </div>
      </label>
    </div>

    <!-- Download button + progress -->
    <div class="space-y-3">
      <button
        :disabled="!hasSelection || state.loading"
        class="w-full flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed"
        @click="download"
      >
        <UIcon v-if="!state.loading" name="i-lucide-download" class="w-4 h-4" />
        <UIcon v-else name="i-lucide-loader-2" class="w-4 h-4 animate-spin" />
        {{ state.loading ? state.progress : t('export.generate') }}
      </button>

      <p v-if="!state.loading && !state.error" class="text-xs text-gray-400 text-center">
        {{ t('export.generatedNote') }}
      </p>
    </div>
  </div>
</template>
