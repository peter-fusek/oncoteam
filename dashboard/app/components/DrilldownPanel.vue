<script setup lang="ts">
const { isOpen, stack, current, detail, loading, error, push, pop, popTo, close } = useDrilldown()

const typeLabels: Record<string, string> = {
  treatment_event: 'Treatment Event',
  research: 'Research Entry',
  conversation: 'Conversation',
  document: 'Document',
  biomarker: 'Biomarker',
  protocol_section: 'Protocol',
  activity: 'Activity',
  patient: 'Patient',
}

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
</script>

<template>
  <USlideover v-model:open="isOpen" side="right" :ui="{ width: 'max-w-lg' }">
    <div class="flex flex-col h-full bg-gray-950">
      <!-- Header with breadcrumb -->
      <div class="p-4 border-b border-gray-800 shrink-0">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2 min-w-0">
            <button v-if="stack.length > 1" class="text-gray-500 hover:text-white" @click="pop">
              <UIcon name="i-lucide-arrow-left" />
            </button>
            <span class="text-lg">{{ typeIcons[current?.type ?? ''] ?? '📌' }}</span>
            <h2 class="text-base font-semibold text-white truncate">{{ current?.label }}</h2>
          </div>
          <button class="text-gray-500 hover:text-white" @click="close">
            <UIcon name="i-lucide-x" />
          </button>
        </div>

        <!-- Breadcrumb -->
        <div v-if="stack.length > 1" class="flex items-center gap-1 text-xs text-gray-500 overflow-x-auto">
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

        <UBadge variant="subtle" size="xs" color="neutral" class="mt-1">
          {{ typeLabels[current?.type ?? ''] ?? current?.type }}
        </UBadge>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto">
        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-16">
          <UIcon name="i-lucide-loader-2" class="text-gray-500 animate-spin w-6 h-6" />
        </div>

        <!-- Error -->
        <div v-else-if="error" class="p-4">
          <div class="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
            {{ error }}
          </div>
        </div>

        <!-- Detail content -->
        <div v-else-if="detail?.data" class="p-4 space-y-4">

          <!-- External link (research entries) -->
          <a
            v-if="detail.data.external_url"
            :href="String(detail.data.external_url)"
            target="_blank"
            class="flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300"
          >
            <UIcon name="i-lucide-external-link" />
            <span>View on {{ detail.data.source === 'pubmed' ? 'PubMed' : 'ClinicalTrials.gov' }}</span>
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

                <!-- Long text (content, notes, summary) -->
                <div v-else-if="['content', 'notes', 'summary', 'raw_data'].includes(String(key)) && String(val).length > 100" class="rounded-lg border border-gray-800 p-3">
                  <div class="text-xs text-gray-500 uppercase tracking-wider mb-2">{{ String(key).replace(/_/g, ' ') }}</div>
                  <div class="text-sm text-gray-300 whitespace-pre-wrap break-words">{{ val }}</div>
                </div>

                <!-- Simple key-value -->
                <div v-else class="flex items-start gap-2 text-sm px-1">
                  <span class="text-gray-500 font-mono text-xs min-w-24 shrink-0">{{ String(key).replace(/_/g, ' ') }}</span>
                  <span class="text-gray-300 break-all">{{ formatValue(val) }}</span>
                </div>
              </template>
            </template>
          </div>
        </div>
      </div>

      <!-- Footer: Source tracing + related -->
      <div v-if="detail && !loading" class="border-t border-gray-800 shrink-0">
        <!-- Related items -->
        <div v-if="detail.related?.length" class="p-3 border-b border-gray-800/50">
          <div class="text-xs text-gray-500 mb-2">Related</div>
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
        <div class="px-4 py-3 text-xs text-gray-600 flex items-center justify-between">
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
            Google Drive
          </a>
        </div>
      </div>
    </div>
  </USlideover>
</template>
