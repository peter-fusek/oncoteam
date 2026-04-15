<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()
const route = useRoute()
const drilldown = useDrilldown()

interface FactItem {
  id: string
  fact_type: string
  category: string
  event_subtype: string
  title: string
  date: string
  summary: string
  source_label: string
  gdrive_url: string | null
  document_id: number | null
  oncofiles_id: number | null
  tags: string[]
  has_document: boolean
}

interface FactsResponse {
  facts: FactItem[]
  total: number
  offset: number
  limit: number
  has_more: boolean
  error?: string
}

// Filter state — hydrated from URL query
const activeCategory = ref((route.query.categories as string) || '')
const searchQuery = ref((route.query.search as string) || '')
const dateFrom = ref((route.query.date_from as string) || '')
const dateTo = ref((route.query.date_to as string) || '')
const sortOrder = ref((route.query.sort as string) || 'newest')

// Accumulated facts for infinite scroll
const allFacts = useState<FactItem[]>('facts-items', () => [])
const currentOffset = ref(0)
const totalFacts = ref(0)
const hasMore = ref(false)
const loadingMore = ref(false)

// Debounced search
const debouncedSearch = ref(searchQuery.value)
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = val }, 400)
})

// Build filter query as a reactive object (useFetch merges with useOncoteamApi query)
const factsQuery = computed(() => {
  const q: Record<string, string> = { sort: sortOrder.value, limit: '20' }
  if (activeCategory.value) q.categories = activeCategory.value
  if (debouncedSearch.value.length >= 3) q.search = debouncedSearch.value
  if (dateFrom.value) q.date_from = dateFrom.value
  if (dateTo.value) q.date_to = dateTo.value
  return q
})

// Serialized key for watch — triggers reset when any filter changes
const filterKey = computed(() => JSON.stringify(factsQuery.value))

const { data: factsData, status: factsStatus, error: factsError, refresh } = useFetch<FactsResponse>(
  '/api/oncoteam/facts',
  {
    query: computed(() => {
      const { activePatientId } = useActivePatient()
      const { locale } = useI18n()
      return { ...factsQuery.value, patient_id: activePatientId.value, lang: locale.value }
    }),
    lazy: true,
    server: false,
    watch: [filterKey],
  },
)

// When filters change, reset accumulated state
watch(filterKey, () => {
  allFacts.value = []
  currentOffset.value = 0
  totalFacts.value = 0
  hasMore.value = false
})

// When new data arrives, populate (immediate: true catches initial load)
watch(factsData, (data) => {
  if (!data?.facts) return
  if (currentOffset.value === 0) {
    allFacts.value = data.facts
  }
  else {
    allFacts.value = [...allFacts.value, ...data.facts]
  }
  totalFacts.value = data.total
  hasMore.value = data.has_more
  loadingMore.value = false
}, { immediate: true })

// Sync filters to URL (replace, not push)
watch([activeCategory, debouncedSearch, dateFrom, dateTo, sortOrder], () => {
  const query: Record<string, string> = {}
  if (activeCategory.value) query.categories = activeCategory.value
  if (debouncedSearch.value) query.search = debouncedSearch.value
  if (dateFrom.value) query.date_from = dateFrom.value
  if (dateTo.value) query.date_to = dateTo.value
  if (sortOrder.value !== 'newest') query.sort = sortOrder.value
  navigateTo({ query }, { replace: true })
})

// Load more (infinite scroll)
async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  currentOffset.value += 20
  const { activePatientId } = useActivePatient()
  const { locale } = useI18n()
  const q = { ...factsQuery.value, offset: String(currentOffset.value), patient_id: activePatientId.value, lang: locale.value }
  const qs = new URLSearchParams(q).toString()
  try {
    const data = await $fetch<FactsResponse>(`/api/oncoteam/facts?${qs}`)
    if (data?.facts) {
      allFacts.value = [...allFacts.value, ...data.facts]
      hasMore.value = data.has_more
    }
  }
  catch {
    // Silently handle — user can retry
  }
  finally {
    loadingMore.value = false
  }
}

// IntersectionObserver for infinite scroll
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => { if (entries[0]?.isIntersecting) loadMore() },
    { rootMargin: '200px' },
  )
  if (sentinel.value) observer.observe(sentinel.value)
})

onUnmounted(() => {
  observer?.disconnect()
})

watch(sentinel, (el) => {
  if (el && observer) observer.observe(el)
})

// Category helpers
const categories = computed(() => [
  { key: '', label: t('facts.all') },
  { key: 'clinical', label: t('facts.clinical') },
  { key: 'documents', label: t('facts.documents') },
  { key: 'intelligence', label: t('facts.intelligence') },
  { key: 'operational', label: t('facts.operational') },
])

function hasActiveFilters() {
  return activeCategory.value || debouncedSearch.value || dateFrom.value || dateTo.value || sortOrder.value !== 'newest'
}

function clearFilters() {
  activeCategory.value = ''
  searchQuery.value = ''
  debouncedSearch.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  sortOrder.value = 'newest'
}

// Visual helpers
function categoryColor(category: string) {
  switch (category) {
    case 'clinical': return 'border-teal-500 bg-teal-500/20'
    case 'documents': return 'border-amber-500 bg-amber-500/20'
    case 'intelligence': return 'border-indigo-500 bg-indigo-500/20'
    case 'operational': return 'border-gray-400 bg-gray-400/20'
    default: return 'border-gray-300 bg-white'
  }
}

function categoryBadgeColor(category: string): string {
  switch (category) {
    case 'clinical': return 'success'
    case 'documents': return 'warning'
    case 'intelligence': return 'info'
    case 'operational': return 'neutral'
    default: return 'neutral'
  }
}

function factIcon(fact: FactItem): string {
  switch (fact.event_subtype) {
    case 'chemotherapy':
    case 'chemo_cycle': return '💊'
    case 'lab_result':
    case 'lab_work':
    case 'labs': return '🧪'
    case 'surgery': return '🔪'
    case 'consultation': return '🩺'
    case 'scan':
    case 'imaging': return '📡'
    case 'toxicity_log': return '⚠️'
    case 'weight_measurement': return '⚖️'
    case 'medication_log': return '💊'
    case 'autonomous_briefing': return '📋'
    case 'session_summary': return '📝'
    case 'agent_run': return '🤖'
    case 'family_update': return '👨\u200D👩\u200D👧'
    case 'chemo_sheet': return '📄'
    case 'pathology': return '🔬'
    case 'genetics': return '🧬'
    case 'preventive': return '🛡️'
    case 'vaccination': return '💉'
    default: return fact.fact_type === 'document' ? '📁' : '📅'
  }
}

function openFact(fact: FactItem) {
  const prefix = fact.id.split(':')[0]
  const numericId = parseInt(fact.id.split(':')[1])
  const typeMap: Record<string, string> = {
    te: 'treatment_event',
    doc: 'document',
    narr: 'narrative',
    lab: 'treatment_event',
  }
  drilldown.open({ type: typeMap[prefix] || 'treatment_event', id: numericId, label: fact.title })
}

// Month grouping
function groupByMonth(facts: FactItem[]): Array<{ month: string; facts: FactItem[] }> {
  const groups = new Map<string, FactItem[]>()
  for (const fact of facts) {
    const d = fact.date ? new Date(fact.date + 'T00:00:00') : null
    const key = d ? d.toLocaleDateString('en-US', { year: 'numeric', month: 'long' }) : 'Unknown date'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(fact)
  }
  return Array.from(groups.entries()).map(([month, facts]) => ({ month, facts }))
}

const groupedFacts = computed(() => groupByMonth(allFacts.value))
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('facts.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('facts.subtitle', { count: totalFacts }) }}</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          v-if="hasActiveFilters()"
          variant="ghost"
          size="xs"
          color="neutral"
          icon="i-lucide-x"
          @click="clearFilters"
        >
          {{ $t('facts.clearFilters') }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <!-- Filters bar -->
    <div class="space-y-3">
      <!-- Date range + Search — stacks on mobile -->
      <div class="grid grid-cols-1 sm:grid-cols-[auto_auto_1fr_auto] gap-3">
        <div class="flex items-center gap-2">
          <label class="text-xs text-gray-500 shrink-0">{{ $t('facts.from') }}</label>
          <input
            v-model="dateFrom"
            type="date"
            class="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:ring-1 focus:ring-teal-500 focus:border-teal-500 w-full sm:w-auto"
          >
        </div>
        <div class="flex items-center gap-2">
          <label class="text-xs text-gray-500 shrink-0">{{ $t('facts.to') }}</label>
          <input
            v-model="dateTo"
            type="date"
            class="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:ring-1 focus:ring-teal-500 focus:border-teal-500 w-full sm:w-auto"
          >
        </div>
        <div>
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="$t('facts.searchPlaceholder')"
            class="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
          >
        </div>
        <select
          v-model="sortOrder"
          class="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 w-full sm:w-auto"
        >
          <option value="newest">{{ $t('facts.newest') }}</option>
          <option value="oldest">{{ $t('facts.oldest') }}</option>
        </select>
      </div>

      <!-- Category chips — scrollable on mobile -->
      <div class="flex flex-wrap gap-2">
        <UButton
          v-for="cat in categories"
          :key="cat.key"
          size="xs"
          :variant="activeCategory === cat.key ? 'solid' : 'ghost'"
          :color="activeCategory === cat.key ? 'primary' : 'neutral'"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
        </UButton>
      </div>
    </div>

    <ApiErrorBanner :error="factsData?.error || factsError?.message" />
    <SkeletonLoader v-if="!factsData && factsStatus === 'pending'" variant="cards" />

    <!-- Fact feed -->
    <div v-if="groupedFacts.length" class="relative pl-6">
      <!-- Vertical line -->
      <div class="absolute left-2 top-2 bottom-2 w-px bg-gray-100" />

      <template v-for="group in groupedFacts" :key="group.month">
        <!-- Month separator -->
        <div class="relative pb-3 pt-1">
          <div class="absolute -left-4 top-2.5 w-3 h-3 rounded-full bg-gray-200 border-2 border-gray-300" />
          <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">{{ group.month }}</span>
        </div>

        <div v-for="fact in group.facts" :key="fact.id" class="relative pb-4 last:pb-0">
          <!-- Category dot -->
          <div class="absolute -left-4 top-3 w-3 h-3 rounded-full border-2" :class="categoryColor(fact.category)" />

          <div
            class="rounded-lg border border-gray-200 bg-white p-3 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
            @click="openFact(fact)"
          >
            <div class="flex items-start gap-2.5">
              <span class="text-base mt-0.5">{{ factIcon(fact) }}</span>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="font-medium text-gray-900 text-sm truncate">{{ fact.title }}</span>
                  <UBadge variant="subtle" size="xs" :color="categoryBadgeColor(fact.category)">
                    {{ fact.event_subtype.replace(/_/g, ' ') }}
                  </UBadge>
                </div>
                <div class="flex items-center gap-2 mt-1 flex-wrap">
                  <span class="text-xs text-gray-500">{{ formatDate(fact.date) }}</span>
                  <span class="text-xs text-gray-300 hidden sm:inline">&middot;</span>
                  <span class="text-xs text-gray-400">{{ fact.category }}</span>
                  <a
                    v-if="fact.gdrive_url"
                    :href="fact.gdrive_url"
                    target="_blank"
                    class="text-xs text-teal-600 hover:text-teal-700 flex items-center gap-0.5"
                    @click.stop
                  >
                    <UIcon name="i-lucide-external-link" class="w-3 h-3" />
                    {{ $t('facts.gdrive') }}
                  </a>
                </div>
                <p v-if="fact.summary" class="text-xs text-gray-500 mt-1.5 line-clamp-2">{{ fact.summary }}</p>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Sentinel for infinite scroll -->
      <div ref="sentinel" class="h-1" />

      <!-- Load more indicator -->
      <div v-if="loadingMore" class="flex justify-center py-4">
        <UIcon name="i-lucide-loader-2" class="w-5 h-5 text-gray-400 animate-spin" />
      </div>
      <div v-else-if="hasMore" class="flex justify-center py-4">
        <UButton variant="ghost" size="xs" color="neutral" @click="loadMore">
          {{ $t('facts.loadMore', { loaded: allFacts.length, total: totalFacts }) }}
        </UButton>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="factsStatus !== 'pending' && !factsError" class="text-center py-16">
      <UIcon name="i-lucide-inbox" class="w-10 h-10 text-gray-300 mx-auto mb-3" />
      <p class="text-sm text-gray-500">{{ $t('facts.noResults') }}</p>
      <UButton v-if="hasActiveFilters()" variant="ghost" size="xs" color="neutral" class="mt-2" @click="clearFilters">
        {{ $t('facts.clearFilters') }}
      </UButton>
    </div>
  </div>
</template>
