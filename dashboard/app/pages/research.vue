<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const activeTab = ref<'trials' | 'literature'>('trials')
const sortBy = ref<'relevance' | 'date' | 'source'>('relevance')

// Watched trials from clinical protocol
const { data: protocol } = fetchApi<{
  watched_trials: string[]
}>('/protocol', { lazy: true })

const { data: research, status: researchStatus, error: researchError, refresh } = fetchApi<{
  entries: Array<{
    id: number
    source: string
    external_id: string
    title: string
    summary: string
    date: string | null
    external_url: string | null
    relevance: 'high' | 'medium' | 'low' | 'not_applicable'
    relevance_reason: string
  }>
  total: number
  error?: string
}>('/research?per_page=100&sort=relevance', { lazy: true })

// Split entries into trials and literature
const trialEntries = computed(() => {
  if (!research.value?.entries) return []
  return research.value.entries.filter(e => e.source === 'clinicaltrials')
})

const literatureEntries = computed(() => {
  if (!research.value?.entries) return []
  return research.value.entries.filter(e => e.source !== 'clinicaltrials')
})

const displayEntries = computed(() => {
  const entries = activeTab.value === 'trials' ? trialEntries.value : literatureEntries.value
  if (sortBy.value === 'date') {
    return [...entries].sort((a, b) => (b.date || '').localeCompare(a.date || ''))
  }
  return entries // Already sorted by relevance from API
})

// Relevance stats
const highRelevanceCount = computed(() =>
  research.value?.entries?.filter(e => e.relevance === 'high').length ?? 0,
)

const relevanceIcon: Record<string, string> = {
  high: 'i-lucide-star',
  medium: 'i-lucide-circle-dot',
  low: 'i-lucide-circle',
  not_applicable: 'i-lucide-circle-x',
}

const relevanceColor: Record<string, string> = {
  high: 'text-amber-600',
  medium: 'text-blue-500',
  low: 'text-gray-400',
  not_applicable: 'text-gray-300',
}

const relevanceBadgeColor: Record<string, string> = {
  high: 'success',
  medium: 'info',
  low: 'neutral',
  not_applicable: 'error',
}

function sourceIcon(source: string): string {
  if (source === 'pubmed') return 'i-lucide-book-open'
  if (source === 'clinicaltrials') return 'i-lucide-flask-conical'
  if (source === 'esmo') return 'i-lucide-graduation-cap'
  return 'i-lucide-file-text'
}

function sourceLabel(source: string): string {
  if (source === 'pubmed') return 'PubMed'
  if (source === 'clinicaltrials') return 'ClinicalTrials.gov'
  if (source === 'esmo') return 'ESMO'
  if (source === 'manual') return 'Manual'
  return source
}

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('research.title') }}</h1>
        <p class="text-sm text-gray-500">
          {{ research?.total ?? 0 }} entries
          <span v-if="highRelevanceCount" class="text-amber-600 font-medium ml-1">
            ({{ highRelevanceCount }} high relevance)
          </span>
        </p>
        <LastUpdated :timestamp="research?.last_updated" />
      </div>
      <div class="flex items-center gap-2">
        <UButtonGroup>
          <UButton
            :variant="sortBy === 'relevance' ? 'solid' : 'soft'"
            size="xs"
            color="neutral"
            @click="sortBy = 'relevance'"
          >
            {{ $t('research.sortRelevance') }}
          </UButton>
          <UButton
            :variant="sortBy === 'date' ? 'solid' : 'soft'"
            size="xs"
            color="neutral"
            @click="sortBy = 'date'"
          >
            {{ $t('research.sortDate') }}
          </UButton>
        </UButtonGroup>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="research?.error || researchError?.message" />
    <SkeletonLoader v-if="!research && researchStatus === 'pending'" variant="cards" />

    <!-- Watched trials panel (from clinical protocol) -->
    <div v-if="protocol?.watched_trials?.length && activeTab === 'trials'" class="rounded-xl border border-teal-200 bg-teal-50/50 p-4">
      <div class="flex items-center gap-2 mb-3">
        <UIcon name="i-lucide-radar" class="text-teal-700 w-4 h-4" />
        <h2 class="text-sm font-semibold text-teal-900">Actively Monitored Trials</h2>
        <span class="text-[10px] text-teal-600 ml-auto">From clinical protocol</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        <div
          v-for="trial in protocol.watched_trials"
          :key="trial"
          class="flex items-center gap-2 rounded-lg bg-white/80 border border-teal-100 px-3 py-2 text-xs"
        >
          <UIcon name="i-lucide-eye" class="text-teal-500 w-3.5 h-3.5 flex-shrink-0" />
          <span class="text-gray-800 font-medium">{{ trial }}</span>
        </div>
      </div>
    </div>

    <!-- Tab navigation -->
    <div class="flex gap-1 rounded-lg border border-gray-200 p-1 bg-gray-50 w-fit">
      <button
        class="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors"
        :class="activeTab === 'trials'
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'"
        @click="activeTab = 'trials'"
      >
        <UIcon name="i-lucide-flask-conical" class="w-4 h-4" />
        Clinical Trials
        <UBadge v-if="trialEntries.length" variant="subtle" size="xs" color="success">{{ trialEntries.length }}</UBadge>
      </button>
      <button
        class="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors"
        :class="activeTab === 'literature'
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'"
        @click="activeTab = 'literature'"
      >
        <UIcon name="i-lucide-book-open" class="w-4 h-4" />
        Literature
        <UBadge v-if="literatureEntries.length" variant="subtle" size="xs" color="info">{{ literatureEntries.length }}</UBadge>
      </button>
    </div>

    <!-- Entries list -->
    <div v-if="displayEntries.length" class="space-y-3">
      <div
        v-for="entry in displayEntries"
        :key="entry.id"
        class="group rounded-xl border border-gray-200 bg-white p-4 hover:shadow-sm transition-all cursor-pointer"
        :class="entry.relevance === 'high' ? 'ring-1 ring-amber-200/50' : ''"
        @click="drilldown.open({ type: 'research', id: entry.id, label: entry.title })"
      >
        <div class="flex items-start gap-3">
          <!-- Relevance indicator -->
          <div class="flex flex-col items-center gap-1 pt-0.5">
            <UIcon :name="relevanceIcon[entry.relevance]" :class="relevanceColor[entry.relevance]" class="w-5 h-5" />
          </div>

          <div class="min-w-0 flex-1">
            <!-- Title -->
            <h3 class="font-medium text-gray-900 text-sm leading-snug">{{ entry.title }}</h3>

            <!-- Metadata row -->
            <div class="flex items-center gap-2 mt-2 flex-wrap">
              <!-- Source badge -->
              <UBadge variant="subtle" size="xs" :color="entry.source === 'clinicaltrials' ? 'success' : entry.source === 'pubmed' ? 'info' : 'neutral'">
                <UIcon :name="sourceIcon(entry.source)" class="w-3 h-3 mr-0.5" />
                {{ sourceLabel(entry.source) }}
              </UBadge>

              <!-- Relevance badge -->
              <UBadge variant="subtle" size="xs" :color="relevanceBadgeColor[entry.relevance]" :title="entry.relevance_reason">
                <UIcon :name="relevanceIcon[entry.relevance]" class="w-3 h-3 mr-0.5" />
                {{ $t(`research.relevance.${entry.relevance}`) }}
              </UBadge>

              <!-- External ID as clickable link -->
              <a
                v-if="entry.external_url && entry.external_id"
                :href="entry.external_url"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 text-xs font-mono text-teal-700 hover:text-teal-900 bg-teal-50 hover:bg-teal-100 rounded px-1.5 py-0.5 transition-colors"
                :title="`Open ${entry.external_id} in ${sourceLabel(entry.source)}`"
                @click.stop
              >
                {{ entry.external_id }}
                <UIcon name="i-lucide-external-link" class="w-3 h-3" />
              </a>
              <span v-else-if="entry.external_id" class="text-xs font-mono text-gray-400">
                {{ entry.external_id }}
              </span>
            </div>

            <!-- Relevance reason -->
            <p v-if="entry.relevance_reason" class="text-xs text-gray-500 mt-1.5 italic">
              {{ entry.relevance_reason }}
            </p>

            <!-- Summary -->
            <p v-if="entry.summary" class="text-xs text-gray-600 mt-1.5 line-clamp-3 leading-relaxed">
              {{ entry.summary }}
            </p>
          </div>

          <!-- External link button -->
          <a
            v-if="entry.external_url"
            :href="entry.external_url"
            target="_blank"
            rel="noopener"
            class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
            :title="`Open in ${sourceLabel(entry.source)}`"
            @click.stop
          >
            <UButton icon="i-lucide-external-link" variant="ghost" size="xs" color="neutral" />
          </a>
        </div>
      </div>
    </div>

    <div v-else-if="!research?.error && !researchError" class="text-gray-400 text-center py-16 text-sm">
      {{ activeTab === 'trials' ? 'No clinical trials found' : $t('research.noResearch') }}
    </div>
  </div>
</template>
