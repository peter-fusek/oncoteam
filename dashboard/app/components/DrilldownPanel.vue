<script setup lang="ts">
const { isOpen, stack, current, detail, loading, error, push, pop, popTo, close } = useDrilldown()

const { t } = useI18n()

const typeLabels = computed<Record<string, string>>(() => ({
  treatment_event: t('components.drilldown.treatmentEvent'),
  research: t('research.title'),
  conversation: t('sessions.title'),
  document: t('components.drilldown.document'),
  biomarker: t('patient.biomarkers'),
  protocol_section: t('nav.protocol'),
  activity: t('agents.activity'),
  patient: t('nav.patient'),
}))

const typeIcons: Record<string, string> = {
  treatment_event: '📅',
  research: '🔬',
  conversation: '💬',
  document: '📄',
  biomarker: '🧬',
  protocol_section: '📋',
  activity: '⚡',
  patient: '👤',
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object') return JSON.stringify(val, null, 2)
  return String(val)
}

function isObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val)
}

// For activity type: track expanded output sections
const expandedOutputs = ref(new Set<string>())

function toggleOutput(key: string) {
  if (expandedOutputs.value.has(key)) {
    expandedOutputs.value.delete(key)
  } else {
    expandedOutputs.value.add(key)
  }
}

function isActivityType(): boolean {
  return current?.value?.type === 'activity'
}
</script>

<template>
  <USlideover
    v-model:open="isOpen"
    side="right"
    :title="`${typeIcons[current?.type ?? ''] ?? '📌'} ${current?.label ?? ''}`"
    :description="typeLabels[current?.type ?? ''] ?? current?.type ?? ''"
    :ui="{ width: 'max-w-lg' }"
    @update:open="(val: boolean) => { if (!val) close() }"
  >
    <template #body>
    <!-- Breadcrumb -->
    <div v-if="stack.length > 1" class="flex items-center gap-1 text-xs text-gray-500 overflow-x-auto px-4 pb-2">
      <template v-for="(item, i) in stack" :key="i">
        <span v-if="i > 0" class="text-gray-700">/</span>
        <button
          class="hover:text-white truncate max-w-32 transition-colors"
          :class="i === stack.length - 1 ? 'text-teal-400' : ''"
          @click="popTo(i)"
        >
          {{ item.label }}
        </button>
      </template>
    </div>

    <!-- Back button -->
    <div v-if="stack.length > 1" class="px-4 pb-2">
      <button class="text-xs text-gray-500 hover:text-white flex items-center gap-1" @click="pop">
        <UIcon name="i-lucide-arrow-left" class="w-3 h-3" />
        {{ t('components.drilldown.back') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-16">
      <UIcon name="i-lucide-loader-2" class="text-gray-500 animate-spin w-6 h-6" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="px-4 pb-4">
      <div class="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
        {{ error }}
      </div>
    </div>

    <!-- Detail content -->
    <div v-else-if="detail?.data" class="px-4 pb-4 space-y-4">

      <!-- Research: relevance badge + external link -->
      <div v-if="detail.data.relevance" class="flex items-center gap-3 flex-wrap">
        <UBadge
          variant="subtle"
          size="xs"
          :color="({ high: 'success', medium: 'info', low: 'neutral', not_applicable: 'error' } as Record<string, string>)[String(detail.data.relevance)] ?? 'neutral'"
        >
          {{ t(`research.relevance.${detail.data.relevance}`) }}
        </UBadge>
        <span v-if="detail.data.relevance_reason" class="text-xs text-gray-500">
          {{ detail.data.relevance_reason }}
        </span>
      </div>

      <!-- External link (research entries) -->
      <a
        v-if="detail.data.external_url"
        :href="String(detail.data.external_url)"
        target="_blank"
        class="flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300"
      >
        <UIcon name="i-lucide-external-link" />
        <span>{{ detail.data.source === 'pubmed' ? t('components.drilldown.viewOnPubMed') : t('components.drilldown.viewOnClinicalTrials') }}</span>
      </a>

      <!-- Render data fields -->
      <div class="space-y-3">
        <template v-for="(val, key) in detail.data" :key="key">
          <!-- Skip internal fields -->
          <template v-if="!['external_url'].includes(String(key))">
            <!-- Nested object -->
            <div v-if="isObject(val)" class="rounded-lg border border-gray-800 p-3">
              <div class="text-xs text-gray-500 uppercase tracking-wider mb-2">{{ String(key).replace(/_/g, ' ') }}</div>
              <div class="space-y-1.5">
                <div v-for="(subVal, subKey) in (val as Record<string, unknown>)" :key="subKey" class="flex items-start gap-2 text-sm">
                  <span class="text-gray-500 font-mono text-xs min-w-24 shrink-0">{{ String(subKey).replace(/_/g, ' ') }}</span>
                  <span class="text-gray-300 break-all">{{ formatValue(subVal) }}</span>
                </div>
              </div>
            </div>

            <!-- Array -->
            <div v-else-if="Array.isArray(val)" class="rounded-lg border border-gray-800 p-3">
              <div class="text-xs text-gray-500 uppercase tracking-wider mb-2">{{ String(key).replace(/_/g, ' ') }}</div>
              <div v-for="(item, i) in (val as unknown[])" :key="i" class="text-sm text-gray-300 py-0.5">
                <template v-if="isObject(item)">
                  <div class="rounded bg-gray-800/50 p-2 mb-1">
                    <div v-for="(v, k) in (item as Record<string, unknown>)" :key="k" class="flex gap-2 text-xs">
                      <span class="text-gray-500 font-mono">{{ k }}</span>
                      <span class="text-gray-300">{{ formatValue(v) }}</span>
                    </div>
                  </div>
                </template>
                <template v-else>{{ formatValue(item) }}</template>
              </div>
            </div>

            <!-- Activity output: full display with collapsible section -->
            <div v-else-if="isActivityType() && ['output', 'input'].includes(String(key)) && String(val).length > 100" class="rounded-lg border border-gray-800 p-3">
              <div class="flex items-center justify-between mb-2">
                <div class="text-xs text-gray-500 uppercase tracking-wider">{{ String(key).replace(/_/g, ' ') }}</div>
                <button
                  v-if="String(val).length > 500"
                  class="text-[10px] text-teal-400 hover:text-teal-300"
                  @click="toggleOutput(String(key))"
                >
                  {{ expandedOutputs.has(String(key)) ? t('agents.collapseOutput') : t('agents.showFullOutput') }}
                </button>
              </div>
              <div
                class="text-sm text-gray-300 whitespace-pre-wrap break-words overflow-auto"
                :class="!expandedOutputs.has(String(key)) && String(val).length > 500 ? 'max-h-32' : 'max-h-[70vh]'"
              >{{ val }}</div>
            </div>

            <!-- Long text (content, notes, summary) -->
            <div v-else-if="['content', 'notes', 'summary', 'raw_data'].includes(String(key)) && String(val).length > 100" class="rounded-lg border border-gray-800 p-3">
              <div class="text-xs text-gray-500 uppercase tracking-wider mb-2">{{ String(key).replace(/_/g, ' ') }}</div>
              <div class="text-sm text-gray-300 whitespace-pre-wrap break-words">{{ val }}</div>
            </div>

            <!-- Simple key-value -->
            <div v-else class="flex items-start gap-2 text-sm px-1">
              <span class="text-gray-500 font-mono text-xs min-w-24 shrink-0">{{ String(key).replace(/_/g, ' ') }}</span>
              <NuxtLink
                v-if="String(key) === 'document_id'"
                :to="'/documents?id=' + val"
                class="text-teal-400 hover:text-teal-300 break-all"
              >Doc #{{ val }}</NuxtLink>
              <span v-else class="text-gray-300 break-all">{{ formatValue(val) }}</span>
            </div>
          </template>
        </template>
      </div>

      <!-- Related items -->
      <div v-if="detail.related?.length" class="pt-3 border-t border-gray-800">
        <div class="text-xs text-gray-500 mb-2">{{ t('components.drilldown.related') }}</div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="rel in detail.related"
            :key="`${rel.type}-${rel.id}`"
            class="text-xs px-2 py-1 rounded-full border border-gray-700 hover:border-teal-500/50 text-gray-400 hover:text-white transition-colors"
            @click="push({ type: rel.type, id: rel.id, label: rel.label })"
          >
            {{ typeIcons[rel.type] ?? '📌' }} {{ rel.label }}
          </button>
        </div>
      </div>

      <!-- Source tracing -->
      <div class="pt-3 border-t border-gray-800 text-xs text-gray-600 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span v-if="detail.source?.oncofiles_id">
            <span class="text-gray-500">ID:</span> {{ detail.source.oncofiles_id }}
          </span>
          <span v-if="detail.type" class="text-gray-700">{{ detail.type }}</span>
        </div>
        <a
          v-if="detail.source?.gdrive_url"
          :href="detail.source.gdrive_url"
          target="_blank"
          class="flex items-center gap-1 text-teal-500 hover:text-teal-400"
        >
          <UIcon name="i-lucide-download" class="w-3 h-3" />
          {{ t('common.googleDrive') }}
        </a>
      </div>
    </div>
    </template>
  </USlideover>
</template>
