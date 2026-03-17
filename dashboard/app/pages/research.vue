<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const currentPage = ref(1)
const perPage = ref(10)
const sortBy = ref<'relevance' | 'date' | 'source'>('relevance')
const sourceFilter = ref<string | null>(null)

const apiUrl = computed(() => {
  const params = new URLSearchParams({
    page: String(currentPage.value),
    per_page: String(perPage.value),
    sort: sortBy.value,
  })
  if (sourceFilter.value) {
    params.set('source', sourceFilter.value)
  }
  return `/research?${params.toString()}`
})

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
  page: number
  per_page: number
  total_pages: number
  error?: string
}>(apiUrl, { lazy: true, watch: [apiUrl] })

const showingFrom = computed(() => {
  if (!research.value?.total) return 0
  return (research.value.page - 1) * research.value.per_page + 1
})

const showingTo = computed(() => {
  if (!research.value?.total) return 0
  return Math.min(research.value.page * research.value.per_page, research.value.total)
})

function setSourceFilter(value: string | null) {
  sourceFilter.value = value
  currentPage.value = 1
}

function setSort(value: 'relevance' | 'date' | 'source') {
  sortBy.value = value
  currentPage.value = 1
}

function prevPage() {
  if (currentPage.value > 1) currentPage.value--
}

function nextPage() {
  if (research.value && currentPage.value < research.value.total_pages) currentPage.value++
}

const relevanceColor: Record<string, string> = {
  high: 'success',
  medium: 'info',
  low: 'neutral',
  not_applicable: 'error',
}

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('research.title') }}</h1>
        <p class="text-sm text-gray-400">
          <template v-if="research?.total">
            {{ $t('research.showing', { from: showingFrom, to: showingTo, total: research.total }) }}
          </template>
          <template v-else>
            {{ $t('research.count', { count: research?.total ?? 0 }) }}
          </template>
        </p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <!-- Sort dropdown -->
        <UButtonGroup>
          <UButton
            :variant="sortBy === 'relevance' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSort('relevance')"
          >
            {{ $t('research.sortRelevance') }}
          </UButton>
          <UButton
            :variant="sortBy === 'date' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSort('date')"
          >
            {{ $t('research.sortDate') }}
          </UButton>
          <UButton
            :variant="sortBy === 'source' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSort('source')"
          >
            {{ $t('research.sortSource') }}
          </UButton>
        </UButtonGroup>
        <!-- Source filter -->
        <UButtonGroup>
          <UButton
            :variant="!sourceFilter ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSourceFilter(null)"
          >
            {{ $t('research.filterAll') }}
          </UButton>
          <UButton
            :variant="sourceFilter === 'pubmed' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSourceFilter('pubmed')"
          >
            PubMed
          </UButton>
          <UButton
            :variant="sourceFilter === 'clinicaltrials' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="setSourceFilter('clinicaltrials')"
          >
            {{ $t('research.filterTrials') }}
          </UButton>
        </UButtonGroup>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="research?.error || researchError?.message" />
    <SkeletonLoader v-if="!research && researchStatus === 'pending'" variant="cards" />

    <div v-if="research?.entries?.length" class="space-y-2">
      <div
        v-for="entry in research.entries"
        :key="entry.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 p-4 hover:bg-gray-800/30 transition-colors cursor-pointer hover:ring-1 hover:ring-teal-500/30"
        @click="drilldown.open({ type: 'research', id: entry.id, label: entry.title })"
      >
        <div class="flex items-start gap-3">
          <span class="text-lg mt-0.5">{{ entry.source === 'pubmed' ? '📄' : '🧪' }}</span>
          <div class="min-w-0 flex-1">
            <div class="font-medium text-white text-sm">{{ entry.title }}</div>
            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              <UBadge
                variant="subtle"
                size="xs"
                :color="entry.source === 'pubmed' ? 'info' : 'success'"
              >
                {{ entry.source === 'pubmed' ? $t('research.sourcePubMed') : $t('research.sourceClinicalTrials') }}
              </UBadge>
              <UBadge
                variant="subtle"
                size="xs"
                :color="relevanceColor[entry.relevance] ?? 'neutral'"
                :title="entry.relevance_reason"
              >
                {{ $t(`research.relevance.${entry.relevance}`) }}
              </UBadge>
              <span v-if="entry.external_id" class="text-xs font-mono text-gray-500">
                {{ entry.external_id }}
              </span>
              <a
                v-if="entry.external_url"
                :href="entry.external_url"
                target="_blank"
                class="text-xs text-teal-500 hover:text-teal-400"
                @click.stop
              >
                {{ $t('common.viewSource') }} ↗
              </a>
            </div>
            <p v-if="entry.relevance_reason" class="text-xs text-gray-600 mt-1">
              {{ entry.relevance_reason }}
            </p>
            <p v-if="entry.summary" class="text-xs text-gray-500 mt-1.5 line-clamp-2">
              {{ entry.summary }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!research?.error && !researchError" class="text-gray-600 text-center py-16 text-sm">
      {{ $t('research.noResearch') }}
    </div>

    <!-- Pagination controls -->
    <div v-if="research && research.total_pages > 1" class="flex items-center justify-center gap-3 pt-2">
      <UButton
        :disabled="currentPage <= 1"
        variant="ghost"
        size="xs"
        color="neutral"
        @click="prevPage"
      >
        {{ $t('research.previous') }}
      </UButton>
      <span class="text-sm text-gray-400">
        {{ $t('research.pageOf', { page: research.page, totalPages: research.total_pages }) }}
      </span>
      <UButton
        :disabled="currentPage >= research.total_pages"
        variant="ghost"
        size="xs"
        color="neutral"
        @click="nextPage"
      >
        {{ $t('research.next') }}
      </UButton>
    </div>
  </div>
</template>
