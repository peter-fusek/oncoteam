<script setup lang="ts">
const { t } = useI18n()
const { fetchApi } = useOncoteamApi()

const activeCategory = ref<'all' | 'treatment_updates' | 'clinical_news' | 'patient_education'>('all')
const sortBy = ref<'relevance' | 'date'>('relevance')

interface ResearchEntry {
  id: number
  source: string
  external_id: string
  title: string
  summary: string
  date: string | null
  external_url: string | null
  relevance: 'high' | 'medium' | 'low' | 'not_applicable'
  relevance_reason: string
}

const { data: research, status: researchStatus, error: researchError } = fetchApi<{
  entries: ResearchEntry[]
  total: number
  error?: string
}>('/research?per_page=100&sort=relevance', { lazy: true, server: false })

// Classification regex patterns
const TREATMENT_REGEX = /phase\s*(III|3|II|2)|randomized|efficacy|first[- ]line|second[- ]line|chemotherapy|folfox|mfolfox|immunotherapy|bevacizumab|cetuximab|pembrolizumab|nivolumab|survival|overall\s+survival|progression[- ]free|response\s+rate|adjuvant|neoadjuvant|oxaliplatin|irinotecan|capecitabine/i
const CLINICAL_NEWS_REGEX = /NCT\d+|recruiting|enrollment|enroll|open[- ]label|dose[- ]escalation|expanded\s+access|compassionate\s+use/i

function classifyEntry(entry: ResearchEntry): 'treatment_updates' | 'clinical_news' | 'patient_education' {
  const text = `${entry.title} ${entry.summary}`

  // Clinical trials source is always clinical news
  if (entry.source === 'clinicaltrials') return 'clinical_news'

  // High relevance or matches treatment keywords
  if (entry.relevance === 'high' || TREATMENT_REGEX.test(text)) return 'treatment_updates'

  // Matches clinical news keywords
  if (CLINICAL_NEWS_REGEX.test(text)) return 'clinical_news'

  // Everything else is patient education
  return 'patient_education'
}

const classifiedEntries = computed(() => {
  if (!research.value?.entries) return []
  return research.value.entries.map(entry => ({
    ...entry,
    category: classifyEntry(entry),
  }))
})

const filteredEntries = computed(() => {
  let entries = classifiedEntries.value
  if (activeCategory.value !== 'all') {
    entries = entries.filter(e => e.category === activeCategory.value)
  }
  if (sortBy.value === 'date') {
    return [...entries].sort((a, b) => (b.date || '').localeCompare(a.date || ''))
  }
  return entries
})

const categoryCounts = computed(() => ({
  all: classifiedEntries.value.length,
  treatment_updates: classifiedEntries.value.filter(e => e.category === 'treatment_updates').length,
  clinical_news: classifiedEntries.value.filter(e => e.category === 'clinical_news').length,
  patient_education: classifiedEntries.value.filter(e => e.category === 'patient_education').length,
}))

const relevanceBadgeColor: Record<string, string> = {
  high: 'success',
  medium: 'info',
  low: 'neutral',
  not_applicable: 'error',
}

function sourceLabel(source: string): string {
  if (source === 'pubmed') return 'PubMed'
  if (source === 'clinicaltrials') return 'ClinicalTrials.gov'
  if (source === 'esmo') return 'ESMO'
  if (source === 'manual') return 'Manual'
  return source
}

function sourceIcon(source: string): string {
  if (source === 'pubmed') return 'i-lucide-book-open'
  if (source === 'clinicaltrials') return 'i-lucide-flask-conical'
  if (source === 'esmo') return 'i-lucide-graduation-cap'
  return 'i-lucide-file-text'
}

const categoryTabs = computed(() => [
  { key: 'all' as const, label: t('news.allCategories'), count: categoryCounts.value.all },
  { key: 'treatment_updates' as const, label: t('news.treatmentUpdates'), count: categoryCounts.value.treatment_updates },
  { key: 'clinical_news' as const, label: t('news.clinicalNews'), count: categoryCounts.value.clinical_news },
  { key: 'patient_education' as const, label: t('news.patientEducation'), count: categoryCounts.value.patient_education },
])

function formatDate(dateStr: string | null): string {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  }
  catch {
    return dateStr
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('news.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('news.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <UButtonGroup>
          <UButton
            :variant="sortBy === 'relevance' ? 'solid' : 'soft'"
            size="xs"
            color="neutral"
            @click="sortBy = 'relevance'"
          >
            {{ $t('news.sortRelevance') }}
          </UButton>
          <UButton
            :variant="sortBy === 'date' ? 'solid' : 'soft'"
            size="xs"
            color="neutral"
            @click="sortBy = 'date'"
          >
            {{ $t('news.sortDate') }}
          </UButton>
        </UButtonGroup>
      </div>
    </div>

    <ApiErrorBanner :error="research?.error || researchError?.message" />
    <SkeletonLoader v-if="!research && researchStatus === 'pending'" variant="cards" />

    <!-- Category filter tabs -->
    <div v-if="research" class="flex gap-1 rounded-lg border border-gray-200 p-1 bg-gray-50 w-fit flex-wrap">
      <button
        v-for="tab in categoryTabs"
        :key="tab.key"
        class="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors"
        :class="activeCategory === tab.key
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'"
        @click="activeCategory = tab.key"
      >
        {{ tab.label }}
        <UBadge v-if="tab.count" variant="subtle" size="xs" :color="activeCategory === tab.key ? 'success' : 'neutral'">
          {{ tab.count }}
        </UBadge>
      </button>
    </div>

    <!-- Card grid -->
    <div v-if="filteredEntries.length" class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <a
        v-for="entry in filteredEntries"
        :key="entry.id"
        :href="entry.external_url || undefined"
        :target="entry.external_url ? '_blank' : undefined"
        rel="noopener"
        class="group rounded-xl border border-gray-200 bg-white p-4 hover:shadow-md transition-all"
        :class="[
          entry.external_url ? 'cursor-pointer' : 'cursor-default',
          entry.relevance === 'high' ? 'ring-1 ring-amber-200/50' : '',
        ]"
        @click.prevent="entry.external_url ? window.open(entry.external_url, '_blank', 'noopener') : undefined"
      >
        <!-- Badges row -->
        <div class="flex items-center gap-2 mb-2 flex-wrap">
          <UBadge variant="subtle" size="xs" :color="entry.source === 'clinicaltrials' ? 'success' : entry.source === 'pubmed' ? 'info' : 'neutral'">
            <UIcon :name="sourceIcon(entry.source)" class="w-3 h-3 mr-0.5" />
            {{ sourceLabel(entry.source) }}
          </UBadge>
          <UBadge variant="subtle" size="xs" :color="relevanceBadgeColor[entry.relevance]">
            {{ $t(`research.relevance.${entry.relevance}`) }}
          </UBadge>
          <span v-if="entry.date" class="text-xs text-gray-400 ml-auto">{{ formatDate(entry.date) }}</span>
        </div>

        <!-- Title -->
        <h3 class="font-medium text-gray-900 text-sm leading-snug line-clamp-2 group-hover:text-teal-700 transition-colors">
          {{ entry.title }}
        </h3>

        <!-- Summary -->
        <p v-if="entry.summary" class="text-xs text-gray-500 mt-1.5 line-clamp-2 leading-relaxed">
          {{ entry.summary }}
        </p>

        <!-- External link indicator -->
        <div v-if="entry.external_url" class="flex items-center gap-1 mt-3 text-xs text-teal-600 opacity-0 group-hover:opacity-100 transition-opacity">
          <UIcon name="i-lucide-external-link" class="w-3 h-3" />
          <span>{{ sourceLabel(entry.source) }}</span>
        </div>
        <div v-else class="mt-3 text-xs text-gray-300">
          {{ $t('news.noLink') }}
        </div>
      </a>
    </div>

    <!-- Empty state -->
    <div v-else-if="research && !research.error && !researchError" class="text-gray-400 text-center py-16 text-sm">
      {{ $t('news.noArticles') }}
    </div>
  </div>
</template>
