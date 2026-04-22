<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()
const { activePatientId } = useActivePatient()

interface ImagingDoc {
  id: number
  filename: string
  category: string
  document_date: string | null
  institution: string | null
  gdrive_url: string | null
  ai_summary?: string
  file_id?: string
}

// Query category=imaging directly so we get full document envelopes from
// search_documents (not the status-matrix shape). Previously the page asked
// for /documents (status matrix) then filtered client-side, which returned
// 0 imaging docs because the matrix truncated the tail of the catalog (#376).
const { data: docsData, status, error: fetchError, refresh, forceRefresh } = fetchApi<{
  documents: ImagingDoc[]
  total: number
  error?: string
}>('/documents?category=imaging&limit=100', { lazy: true, server: false })

const imagingDocs = computed(() => {
  if (!docsData.value?.documents) return []
  return [...docsData.value.documents].sort(
    (a, b) => (b.document_date || '0000').localeCompare(a.document_date || '0000'),
  )
})

// Selection state (max 2)
const selectedIds = useState<number[]>('imaging-selected', () => [])

// Reset selection on patient switch
watch(activePatientId, () => { selectedIds.value = [] })

const selectedDocs = computed(() =>
  selectedIds.value.map(id => imagingDocs.value.find(d => d.id === id)).filter(Boolean) as ImagingDoc[],
)

function isSelected(id: number): boolean {
  return selectedIds.value.includes(id)
}

function toggleSelect(doc: ImagingDoc) {
  if (selectedIds.value.includes(doc.id)) {
    selectedIds.value = selectedIds.value.filter(id => id !== doc.id)
  }
  else if (selectedIds.value.length < 2) {
    selectedIds.value = [...selectedIds.value, doc.id]
  }
  else {
    selectedIds.value = [selectedIds.value[1], doc.id]
  }
}

// gdrive_url shape: https://drive.google.com/file/d/{id}/view
// Turn it into the /preview variant for inline embedding.
function previewUrl(doc: ImagingDoc): string | null {
  const m = doc.gdrive_url?.match(/\/d\/([^/]+)\//)
  if (!m) return null
  return `https://drive.google.com/file/d/${m[1]}/preview`
}

// Timeline dots
const timeRange = computed(() => {
  const dated = imagingDocs.value.filter(d => d.document_date)
  if (dated.length < 2) return null
  const sorted = [...dated].sort((a, b) => a.document_date!.localeCompare(b.document_date!))
  return { start: sorted[0].document_date!, end: sorted[sorted.length - 1].document_date! }
})

function dateToPercent(dateStr: string): number {
  if (!timeRange.value) return 50
  const d = new Date(dateStr + 'T00:00:00').getTime()
  const s = new Date(timeRange.value.start + 'T00:00:00').getTime()
  const e = new Date(timeRange.value.end + 'T00:00:00').getTime()
  if (e === s) return 50
  return Math.max(2, Math.min(98, ((d - s) / (e - s)) * 100))
}

const timelineDots = computed(() => {
  const seen = new Set<string>()
  return imagingDocs.value
    .filter(d => d.document_date && !seen.has(d.document_date) && seen.add(d.document_date))
    .map(d => ({
      date: d.document_date!,
      left: dateToPercent(d.document_date!),
      count: imagingDocs.value.filter(x => x.document_date === d.document_date).length,
    }))
})

// A dot is "active" when any selected doc shares its date — gives the timeline
// a visual read of which dates are currently loaded in the comparison pane.
function isDotActive(date: string): boolean {
  return selectedDocs.value.some(d => d.document_date === date)
}

function onDotClick(date: string) {
  const doc = imagingDocs.value.find(d => d.document_date === date)
  if (doc) toggleSelect(doc)
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('imaging.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('imaging.subtitle', { count: imagingDocs.length }) }}</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          v-if="selectedIds.length"
          variant="ghost"
          size="xs"
          color="neutral"
          icon="i-lucide-x"
          @click="selectedIds = []"
        >
          {{ $t('imaging.clearSelection') }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" :loading="status === 'pending'" @click="forceRefresh" />
      </div>
    </div>

    <ApiErrorBanner :error="docsData?.error || fetchError?.message" />
    <!-- Gate on `docsData`, not `status === 'pending'`: SSR with server:false
         leaves status='idle', which used to fall through to the empty-state
         branch and then refused to re-render once the client fetch filled in. -->
    <SkeletonLoader v-if="!docsData && !fetchError" variant="cards" />

    <template v-else-if="imagingDocs.length">
      <!-- Timeline bar — click a dot to add/remove that date's scan from the comparison -->
      <div v-if="timeRange" class="space-y-1">
        <p class="text-[11px] text-gray-500 px-1">{{ $t('imaging.timelineHint') }}</p>
        <div class="relative h-10 rounded-lg border border-gray-200 bg-white px-6 flex items-center">
          <div class="absolute left-6 right-6 h-px bg-gray-200" />
          <button
            v-for="dot in timelineDots"
            :key="dot.date"
            type="button"
            class="absolute w-3 h-3 rounded-full border-2 transition-transform -translate-x-1.5 z-10 cursor-pointer hover:scale-150 focus:scale-150 focus:outline-none"
            :class="isDotActive(dot.date) ? 'bg-teal-600 border-teal-200 ring-2 ring-teal-300 scale-125' : 'bg-teal-500 border-white'"
            :style="{ left: `calc(24px + ${dot.left}% * (100% - 48px) / 100)` }"
            :title="`${formatDate(dot.date)} (${dot.count})`"
            :aria-label="`${formatDate(dot.date)} — ${dot.count} ${dot.count === 1 ? 'doc' : 'docs'}`"
            :aria-pressed="isDotActive(dot.date)"
            @click="onDotClick(dot.date)"
          />
          <span class="absolute left-2 text-[8px] text-gray-400">{{ timeRange.start }}</span>
          <span class="absolute right-2 text-[8px] text-gray-400">{{ timeRange.end }}</span>
        </div>
      </div>

      <!-- Comparison panes -->
      <div v-if="selectedDocs.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="doc in selectedDocs" :key="'cmp-' + doc.id" class="rounded-xl border border-gray-200 overflow-hidden">
          <div class="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <div class="min-w-0">
              <div class="font-medium text-gray-900 text-sm truncate">{{ doc.filename }}</div>
              <div class="text-xs text-gray-500 mt-0.5">{{ formatDate(doc.document_date) }} &middot; {{ doc.institution || '—' }}</div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <a v-if="doc.gdrive_url" :href="doc.gdrive_url" target="_blank" @click.stop>
                <UIcon name="i-lucide-external-link" class="w-4 h-4 text-teal-600" />
              </a>
              <button @click="toggleSelect(doc)">
                <UIcon name="i-lucide-x" class="w-4 h-4 text-gray-400 hover:text-gray-700" />
              </button>
            </div>
          </div>
          <iframe
            v-if="previewUrl(doc)"
            :src="previewUrl(doc)"
            class="w-full h-[500px] border-0"
            allow="autoplay"
            loading="lazy"
          />
          <div v-else class="h-[500px] flex items-center justify-center text-gray-400 text-sm">
            {{ $t('imaging.previewUnavailable') }}
          </div>
        </div>
        <div v-if="selectedDocs.length === 1" class="rounded-xl border-2 border-dashed border-gray-200 h-[560px] flex items-center justify-center text-gray-400 text-sm">
          {{ $t('imaging.selectSecond') }}
        </div>
      </div>

      <!-- Document list -->
      <div class="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
        <div
          v-for="doc in imagingDocs"
          :key="doc.id"
          class="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-gray-50 transition-colors"
          :class="isSelected(doc.id) ? 'bg-teal-50 border-l-2 border-l-teal-500' : ''"
          @click="toggleSelect(doc)"
        >
          <div
            class="w-5 h-5 rounded border-2 flex items-center justify-center shrink-0"
            :class="isSelected(doc.id) ? 'bg-teal-500 border-teal-500' : 'border-gray-300'"
          >
            <UIcon v-if="isSelected(doc.id)" name="i-lucide-check" class="w-3 h-3 text-white" />
          </div>
          <UIcon name="i-lucide-scan-line" class="w-4 h-4 text-gray-400 shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="text-sm text-gray-900 truncate">{{ doc.filename }}</div>
            <div class="text-xs text-gray-500">{{ formatDate(doc.document_date) }} &middot; {{ doc.institution || '—' }}</div>
          </div>
          <a v-if="doc.gdrive_url" :href="doc.gdrive_url" target="_blank" @click.stop>
            <UIcon name="i-lucide-external-link" class="w-4 h-4 text-gray-400 hover:text-teal-600" />
          </a>
        </div>
      </div>
    </template>

    <!-- Empty state — reached only when data loaded but no docs matched. -->
    <div v-else-if="!fetchError" class="text-center py-16">
      <UIcon name="i-lucide-scan-line" class="w-10 h-10 text-gray-300 mx-auto mb-3" />
      <p class="text-sm text-gray-500">{{ $t('imaging.noDocuments') }}</p>
    </div>
  </div>
</template>
