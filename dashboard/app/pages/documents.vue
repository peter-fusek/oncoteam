<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()

const activeFilter = ref('all')
const filters = ['all', 'incomplete', 'missing_ocr', 'missing_ai', 'missing_metadata', 'not_synced', 'not_renamed']

const apiUrl = computed(() => {
  const params = new URLSearchParams({ filter: activeFilter.value })
  return `/documents?${params.toString()}`
})

const { data: docs, status: docsStatus, error: docsError, refresh } = fetchApi<{
  documents: Array<{
    id: number
    filename: string
    category: string | null
    ocr_status: string | null
    ai_summary_status: string | null
    metadata_status: string | null
    sync_status: string | null
    renamed: boolean | null
    tags: string[]
    updated_at: string | null
    created_at: string | null
    gdrive_url: string | null
  }>
  total: number
  filter: string
  summary: {
    total: number
    ocr_complete: number
    missing_ocr: number
    missing_metadata: number
  }
  error?: string
}>(apiUrl, { lazy: true, watch: [apiUrl] })

function setFilter(f: string) {
  activeFilter.value = f
}

function statusColor(status: string | null | undefined): string {
  if (!status || status === 'not_attempted') return 'neutral'
  if (status === 'complete' || status === 'synced') return 'success'
  if (status === 'partial' || status === 'in_progress') return 'warning'
  if (status === 'missing' || status === 'incomplete' || status === 'error') return 'error'
  return 'neutral'
}

function statusLabel(status: string | null | undefined): string {
  if (!status) return t('documents.statusNotAttempted')
  const key = `documents.status_${status}`
  const val = t(key)
  // fallback if key not found
  return val === key ? status : val
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('documents.title') }}</h1>
        <p class="text-sm text-gray-500">
          {{ $t('documents.subtitle', { count: docs?.total ?? 0 }) }}
        </p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <ApiErrorBanner :error="docs?.error || docsError?.message" />
    <SkeletonLoader v-if="!docs && docsStatus === 'pending'" variant="cards" />

    <!-- Summary cards -->
    <div v-if="docs?.summary" class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="rounded-lg border border-gray-200 bg-white p-4 text-center">
        <div class="text-2xl font-bold text-gray-900">{{ docs.summary.total }}</div>
        <div class="text-xs text-gray-500 mt-1">{{ $t('documents.totalDocs') }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 text-center">
        <div class="text-2xl font-bold text-emerald-600">{{ docs.summary.ocr_complete }}</div>
        <div class="text-xs text-gray-500 mt-1">{{ $t('documents.ocrComplete') }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 text-center">
        <div class="text-2xl font-bold" :class="docs.summary.missing_ocr > 0 ? 'text-red-600' : 'text-gray-500'">{{ docs.summary.missing_ocr }}</div>
        <div class="text-xs text-gray-500 mt-1">{{ $t('documents.missingOcr') }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 text-center">
        <div class="text-2xl font-bold" :class="docs.summary.missing_metadata > 0 ? 'text-amber-600' : 'text-gray-500'">{{ docs.summary.missing_metadata }}</div>
        <div class="text-xs text-gray-500 mt-1">{{ $t('documents.missingMetadata') }}</div>
      </div>
    </div>

    <!-- Filter pills -->
    <div class="flex flex-wrap gap-2">
      <UButton
        v-for="f in filters"
        :key="f"
        :variant="activeFilter === f ? 'solid' : 'ghost'"
        size="xs"
        color="neutral"
        @click="setFilter(f)"
      >
        {{ $t(`documents.filter_${f}`) }}
      </UButton>
    </div>

    <!-- Document table -->
    <div v-if="docs?.documents?.length" class="rounded-lg border border-gray-200 overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-200 text-gray-500 text-xs">
            <th class="text-left px-4 py-2.5 font-medium">{{ $t('documents.colFilename') }}</th>
            <th class="text-left px-4 py-2.5 font-medium">{{ $t('documents.colCategory') }}</th>
            <th class="text-center px-4 py-2.5 font-medium">{{ $t('documents.colOcr') }}</th>
            <th class="text-center px-4 py-2.5 font-medium">{{ $t('documents.colMetadata') }}</th>
            <th class="text-center px-4 py-2.5 font-medium">{{ $t('documents.colAiSummary') }}</th>
            <th class="text-left px-4 py-2.5 font-medium">{{ $t('documents.colTags') }}</th>
            <th class="text-right px-4 py-2.5 font-medium">{{ $t('documents.colUpdated') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="doc in docs.documents"
            :key="doc.id"
            class="border-b border-gray-100 hover:bg-gray-50 transition-colors"
          >
            <td class="px-4 py-2.5 text-gray-900 max-w-xs truncate">
              <a
                v-if="doc.gdrive_url"
                :href="doc.gdrive_url"
                target="_blank"
                class="hover:text-teal-700 transition-colors"
                :title="doc.filename"
              >
                {{ doc.filename }}
              </a>
              <span v-else :title="doc.filename">{{ doc.filename }}</span>
            </td>
            <td class="px-4 py-2.5">
              <UBadge v-if="doc.category" variant="subtle" size="xs" color="info">
                {{ doc.category }}
              </UBadge>
              <span v-else class="text-gray-500">-</span>
            </td>
            <td class="px-4 py-2.5 text-center">
              <UBadge variant="subtle" size="xs" :color="statusColor(doc.ocr_status)">
                {{ statusLabel(doc.ocr_status) }}
              </UBadge>
            </td>
            <td class="px-4 py-2.5 text-center">
              <UBadge variant="subtle" size="xs" :color="statusColor(doc.metadata_status)">
                {{ statusLabel(doc.metadata_status) }}
              </UBadge>
            </td>
            <td class="px-4 py-2.5 text-center">
              <UBadge variant="subtle" size="xs" :color="statusColor(doc.ai_summary_status)">
                {{ statusLabel(doc.ai_summary_status) }}
              </UBadge>
            </td>
            <td class="px-4 py-2.5">
              <div class="flex flex-wrap gap-1 max-w-xs">
                <UBadge
                  v-for="tag in (doc.tags || []).slice(0, 3)"
                  :key="tag"
                  variant="subtle"
                  size="xs"
                  color="neutral"
                >
                  {{ tag }}
                </UBadge>
                <span v-if="(doc.tags || []).length > 3" class="text-xs text-gray-500">
                  +{{ doc.tags.length - 3 }}
                </span>
              </div>
            </td>
            <td class="px-4 py-2.5 text-right text-gray-500 text-xs whitespace-nowrap">
              {{ doc.updated_at ? formatDate(doc.updated_at) : '-' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="!docs?.error && !docsError && docsStatus !== 'pending'" class="text-gray-500 text-center py-16 text-sm">
      {{ $t('documents.noDocs') }}
    </div>

    <!-- Unavailable state — don't confuse "0 documents" with "backend down" -->
    <div v-if="docs?.unavailable && !docs?.documents?.length" class="text-center py-12 text-sm text-gray-500">
      <p class="text-lg font-medium text-gray-700 mb-2">{{ $t('documents.unavailable') }}</p>
      <p>{{ $t('documents.unavailableHint') }}</p>
      <UButton icon="i-lucide-refresh-cw" variant="soft" size="sm" color="neutral" class="mt-4" @click="refresh">
        {{ $t('common.retry') }}
      </UButton>
    </div>
  </div>
</template>
