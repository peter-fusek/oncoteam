<script setup lang="ts">
/**
 * /research — physician cockpit (#399 Sprint 96 S1).
 *
 * 8 sub-panels in a left-sidebar sub-nav. 4 functional (Inbox / Clinical
 * Funnel / Audit / Re-Surfaced). Literature + News carried over from the
 * previous tab layout. Discussion + Watchlist are stubs labeled "ships
 * next sprint" so the frame reads complete.
 *
 * Role-aware landing panel:
 *   - doctor    → Inbox
 *   - advocate  → Clinical Funnel
 *   - default   → Clinical Funnel
 *
 * Active tab is server-persisted per (patient, user) via
 * GET/POST /api/research/active-tab — cross-device per the #395 principle.
 * Query param ?tab= wins over both server pref and role default.
 */
import type { PendingItem } from '~/components/OncopanelInboxCard.vue'

type TabKey =
  | 'inbox'
  | 'funnel'
  | 'literature'
  | 'news'
  | 'discussion'
  | 'audit'
  | 'watchlist'
  | 'resurfaced'

const { fetchApi, postApi } = useOncoteamApi()
const { activeRole } = useUserRole()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// ── Active tab: query > server > role default ─────────────────────────
const _defaultForRole = (): TabKey => (activeRole.value === 'doctor' ? 'inbox' : 'funnel')
const VALID_TABS: TabKey[] = [
  'inbox',
  'funnel',
  'literature',
  'news',
  'discussion',
  'audit',
  'watchlist',
  'resurfaced',
]
const queryTab = computed<TabKey | null>(() => {
  const q = typeof route.query.tab === 'string' ? route.query.tab : null
  return q && (VALID_TABS as string[]).includes(q) ? (q as TabKey) : null
})

const activeTab = ref<TabKey>(queryTab.value || _defaultForRole())
const savedTabLoaded = ref(false)

const { data: savedTab } = fetchApi<{ tab: TabKey | null }>('/research/active-tab', {
  lazy: true,
  server: false,
})
watch(savedTab, (val) => {
  if (savedTabLoaded.value) return
  savedTabLoaded.value = true
  if (queryTab.value) return  // URL wins — don't override
  if (val?.tab && (VALID_TABS as string[]).includes(val.tab)) {
    activeTab.value = val.tab
  }
})

async function setTab(tab: TabKey) {
  activeTab.value = tab
  router.replace({ query: { ...route.query, tab } })
  try {
    await postApi('/research/active-tab', { tab })
  }
  catch {
    // Non-fatal — local state already updated.
  }
}

// ── Shared data sources ───────────────────────────
const { data: protocol } = fetchApi<{
  watched_trials: string[]
}>('/protocol', { lazy: true, server: false })

const { data: research, status: researchStatus, error: researchError, refresh: refreshResearch } = fetchApi<{
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
  last_updated?: string
  error?: string
}>('/research?per_page=100&sort=relevance', { lazy: true, server: false })

// Inbox: pending oncopanel entries
const { data: inbox, status: inboxStatus, error: inboxError, refresh: refreshInbox } = fetchApi<{
  pending: PendingItem[]
  recent_triaged: PendingItem[]
  count: number
  error?: string
}>('/oncopanel/pending', { lazy: true, server: false })

// Funnel proposals (mirrored in Inbox so physician triages in one place).
const { data: proposalsData } = fetchApi<{ count: number }>('/funnel/proposals', {
  lazy: true,
  server: false,
})

// Re-surfaced events — badge count on the sidebar.
const { data: resurfacedData } = fetchApi<{ count: number }>(
  '/funnel/audit/patient?event_type=re_surfaced&limit=50',
  { lazy: true, server: false },
)

// ── Derived entry lists for Literature + News tabs ─────────────────────
const sortBy = ref<'relevance' | 'date'>('relevance')

const trialEntries = computed(() => research.value?.entries?.filter(e => e.source === 'clinicaltrials') ?? [])
const literatureEntries = computed(() => research.value?.entries?.filter(e => e.source !== 'clinicaltrials') ?? [])

const TREATMENT_REGEX = /phase\s*(III|3|II|2)|randomized|efficacy|first[- ]line|second[- ]line|chemotherapy|folfox|mfolfox|immunotherapy|bevacizumab|cetuximab|pembrolizumab|nivolumab|survival|overall\s+survival|progression[- ]free|response\s+rate|adjuvant|neoadjuvant|oxaliplatin|irinotecan|capecitabine/i
const CLINICAL_NEWS_REGEX = /NCT\d+|recruiting|enrollment|enroll|open[- ]label|dose[- ]escalation|expanded\s+access|compassionate\s+use/i
type NewsCategory = 'all' | 'treatment_updates' | 'clinical_news' | 'patient_education'
const activeNewsCategory = ref<NewsCategory>('all')

function classifyEntry(e: { source: string, title: string, summary: string, relevance: string }): 'treatment_updates' | 'clinical_news' | 'patient_education' {
  const text = `${e.title} ${e.summary}`
  if (e.source === 'clinicaltrials') return 'clinical_news'
  if (e.relevance === 'high' || TREATMENT_REGEX.test(text)) return 'treatment_updates'
  if (CLINICAL_NEWS_REGEX.test(text)) return 'clinical_news'
  return 'patient_education'
}

const classifiedEntries = computed(() =>
  (research.value?.entries ?? []).map(e => ({ ...e, newsCategory: classifyEntry(e) })),
)

const newsCategoryCounts = computed(() => ({
  all: classifiedEntries.value.length,
  treatment_updates: classifiedEntries.value.filter(e => e.newsCategory === 'treatment_updates').length,
  clinical_news: classifiedEntries.value.filter(e => e.newsCategory === 'clinical_news').length,
  patient_education: classifiedEntries.value.filter(e => e.newsCategory === 'patient_education').length,
}))

const newsEntries = computed(() => {
  let entries = classifiedEntries.value
  if (activeNewsCategory.value !== 'all') {
    entries = entries.filter(e => e.newsCategory === activeNewsCategory.value)
  }
  if (sortBy.value === 'date') return [...entries].sort((a, b) => (b.date || '').localeCompare(a.date || ''))
  return entries
})

const readingEntries = computed(() => {
  const entries = activeTab.value === 'literature' ? literatureEntries.value : newsEntries.value
  if (sortBy.value === 'date') return [...entries].sort((a, b) => (b.date || '').localeCompare(a.date || ''))
  return entries
})

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
const relevanceBadgeColor: Record<string, 'success' | 'info' | 'neutral' | 'error'> = {
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

const drilldown = useDrilldown()

// ── Sub-nav definition ─────────────────────────────
interface TabDef {
  key: TabKey
  label: string
  icon: string
  functional: boolean
  badge?: () => number | null
  badgeColor?: 'primary' | 'warning' | 'info' | 'neutral' | 'success'
}

const tabs = computed<TabDef[]>(() => [
  {
    key: 'inbox',
    label: 'Inbox',
    icon: 'i-lucide-inbox',
    functional: true,
    badge: () => (inbox.value?.count ?? 0) + (proposalsData.value?.count ?? 0) || null,
    badgeColor: 'primary',
  },
  { key: 'funnel', label: 'Clinical Funnel', icon: 'i-lucide-kanban', functional: true },
  { key: 'literature', label: 'Literature', icon: 'i-lucide-book-open', functional: true },
  { key: 'news', label: 'News', icon: 'i-lucide-newspaper', functional: true },
  { key: 'discussion', label: 'Discussion', icon: 'i-lucide-message-square', functional: false },
  { key: 'audit', label: 'Audit', icon: 'i-lucide-file-clock', functional: true },
  { key: 'watchlist', label: 'My Watchlist', icon: 'i-lucide-star', functional: false },
  {
    key: 'resurfaced',
    label: 'Re-Surfaced',
    icon: 'i-lucide-rotate-ccw',
    functional: true,
    badge: () => resurfacedData.value?.count || null,
    badgeColor: 'warning',
  },
])

function onInboxTriaged() {
  refreshInbox()
}
</script>

<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('research.title') }}</h1>
        <p class="text-sm text-gray-500">
          Physician cockpit · 8 sub-panels, every action audit-logged
        </p>
        <LastUpdated :timestamp="research?.last_updated" />
      </div>
      <div v-if="activeTab === 'literature' || activeTab === 'news'" class="flex items-center gap-2">
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
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refreshResearch" />
      </div>
    </div>

    <div class="flex flex-col lg:flex-row gap-4">
      <!-- Sub-nav: sidebar on desktop, scrollable top bar on mobile -->
      <nav
        class="lg:w-56 shrink-0 flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible pb-1 lg:pb-0"
        aria-label="Research cockpit navigation"
      >
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-left whitespace-nowrap transition-colors"
          :class="activeTab === tab.key
            ? 'bg-teal-50 text-teal-800 border border-teal-200'
            : tab.functional
              ? 'text-gray-600 hover:bg-gray-50'
              : 'text-gray-400 hover:bg-gray-50'"
          @click="setTab(tab.key)"
        >
          <UIcon :name="tab.icon" class="w-4 h-4 shrink-0" />
          <span class="flex-1">{{ tab.label }}</span>
          <UBadge
            v-if="tab.badge && tab.badge()"
            :color="tab.badgeColor || 'neutral'"
            size="xs"
            variant="subtle"
          >
            {{ tab.badge() }}
          </UBadge>
          <UBadge v-else-if="!tab.functional" size="xs" variant="subtle" color="neutral">
            soon
          </UBadge>
        </button>
      </nav>

      <!-- Panel content -->
      <div class="flex-1 min-w-0 space-y-4">
        <!-- Inbox -->
        <template v-if="activeTab === 'inbox'">
          <div class="space-y-4">
            <div>
              <div class="flex items-baseline gap-2 mb-2">
                <h2 class="text-sm font-semibold text-gray-900">Pending oncopanel extractions</h2>
                <p class="text-xs text-gray-500">
                  Each NGS report waits for physician approval before merging into the patient profile.
                </p>
                <UButton
                  icon="i-lucide-refresh-cw"
                  variant="ghost"
                  size="xs"
                  color="neutral"
                  class="ml-auto"
                  @click="refreshInbox"
                />
              </div>
              <SkeletonLoader v-if="inboxStatus === 'pending' && !inbox" variant="cards" />
              <ApiErrorBanner v-else-if="inboxError || inbox?.error" :error="inbox?.error || inboxError?.message" />
              <EmptyState
                v-else-if="!inbox?.pending?.length"
                icon="i-lucide-check-check"
                message="No pending oncopanel extractions. ✅ You're caught up."
              />
              <div v-else class="space-y-3">
                <OncopanelInboxCard
                  v-for="item in inbox.pending"
                  :key="item.key"
                  :item="item"
                  @triaged="onInboxTriaged"
                />
              </div>
              <details v-if="inbox?.recent_triaged?.length" class="mt-3 text-xs text-gray-500">
                <summary class="cursor-pointer hover:text-gray-700">
                  Recently triaged ({{ inbox.recent_triaged.length }})
                </summary>
                <ul class="mt-2 space-y-1 pl-4">
                  <li v-for="item in inbox.recent_triaged" :key="item.key" class="flex items-center gap-2">
                    <UBadge variant="subtle" size="xs" :color="item.status === 'approved' ? 'success' : 'neutral'">
                      {{ item.status }}
                    </UBadge>
                    <span class="font-mono">doc #{{ item.document_id }}</span>
                    <span class="text-gray-400 italic truncate">{{ item.rationale }}</span>
                  </li>
                </ul>
              </details>
            </div>

            <div class="pt-4 border-t border-gray-100">
              <FunnelProposalsPanel />
            </div>
          </div>
        </template>

        <!-- Clinical Funnel -->
        <template v-else-if="activeTab === 'funnel'">
          <div class="space-y-4">
            <div v-if="protocol?.watched_trials?.length" class="rounded-xl border border-teal-200 bg-teal-50/50 p-4">
              <div class="flex items-center gap-2 mb-3">
                <UIcon name="i-lucide-radar" class="text-teal-700 w-4 h-4" />
                <h2 class="text-sm font-semibold text-teal-900">{{ t('research.watchedTrials') }}</h2>
                <span class="text-[10px] text-teal-600 ml-auto">{{ t('research.fromProtocol') }}</span>
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
            <FunnelProposalsPanel />
            <TrialFunnelBoard :trials="trialEntries" :watched-trials="protocol?.watched_trials || []" />
          </div>
        </template>

        <!-- Literature / News (shared renderer) -->
        <template v-else-if="activeTab === 'literature' || activeTab === 'news'">
          <div class="space-y-3">
            <div v-if="activeTab === 'news'" class="flex gap-1 rounded-lg border border-gray-200 p-1 bg-gray-50 w-fit flex-wrap">
              <button
                v-for="cat in (['all', 'treatment_updates', 'clinical_news', 'patient_education'] as const)"
                :key="cat"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                :class="activeNewsCategory === cat ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
                @click="activeNewsCategory = cat"
              >
                {{ t(`news.${cat === 'all' ? 'allCategories' : cat === 'treatment_updates' ? 'treatmentUpdates' : cat === 'clinical_news' ? 'clinicalNews' : 'patientEducation'}`) }}
                <UBadge variant="subtle" size="xs" :color="activeNewsCategory === cat ? 'success' : 'neutral'">
                  {{ newsCategoryCounts[cat] }}
                </UBadge>
              </button>
            </div>

            <ApiErrorBanner :error="research?.error || researchError?.message" />
            <SkeletonLoader v-if="!research && researchStatus === 'pending'" variant="cards" />

            <div v-if="readingEntries.length" class="space-y-3">
              <div
                v-for="entry in readingEntries"
                :key="entry.id"
                class="group rounded-xl border border-gray-200 bg-white p-4 hover:shadow-sm transition-all cursor-pointer"
                :class="entry.relevance === 'high' ? 'ring-1 ring-amber-200/50' : ''"
                @click="drilldown.open({ type: 'research', id: entry.id, label: entry.title, data: { ...entry } })"
              >
                <div class="flex items-start gap-3">
                  <div class="flex flex-col items-center gap-1 pt-0.5">
                    <UIcon :name="relevanceIcon[entry.relevance]" :class="relevanceColor[entry.relevance]" class="w-5 h-5" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <h3 class="font-medium text-gray-900 text-sm leading-snug">{{ entry.title }}</h3>
                    <div class="flex items-center gap-2 mt-2 flex-wrap">
                      <UBadge variant="subtle" size="xs" :color="entry.source === 'clinicaltrials' ? 'success' : entry.source === 'pubmed' ? 'info' : 'neutral'">
                        <UIcon :name="sourceIcon(entry.source)" class="w-3 h-3 mr-0.5" />
                        {{ sourceLabel(entry.source) }}
                      </UBadge>
                      <UBadge variant="subtle" size="xs" :color="relevanceBadgeColor[entry.relevance]" :title="entry.relevance_reason">
                        <UIcon :name="relevanceIcon[entry.relevance]" class="w-3 h-3 mr-0.5" />
                        {{ $t(`research.relevance.${entry.relevance}`) }}
                      </UBadge>
                      <a
                        v-if="entry.external_url && entry.external_id"
                        :href="entry.external_url"
                        target="_blank"
                        rel="noopener"
                        class="inline-flex items-center gap-1 text-xs font-mono text-teal-700 hover:text-teal-900 bg-teal-50 hover:bg-teal-100 rounded px-1.5 py-0.5 transition-colors"
                        @click.stop
                      >
                        {{ entry.external_id }}
                        <UIcon name="i-lucide-external-link" class="w-3 h-3" />
                      </a>
                    </div>
                    <p v-if="entry.relevance_reason" class="text-xs text-gray-500 mt-1.5 italic">{{ entry.relevance_reason }}</p>
                    <p v-if="entry.summary" class="text-xs text-gray-600 mt-1.5 line-clamp-3 leading-relaxed">{{ entry.summary }}</p>
                  </div>
                </div>
              </div>
            </div>
            <EmptyState
              v-else-if="!research?.error && !researchError"
              icon="i-lucide-microscope"
              :message="activeTab === 'literature' ? t('research.noResearch') : t('research.noResearch')"
            />
          </div>
        </template>

        <!-- Audit -->
        <template v-else-if="activeTab === 'audit'">
          <PatientAuditLog />
        </template>

        <!-- Re-Surfaced -->
        <template v-else-if="activeTab === 'resurfaced'">
          <ResurfacedPanel />
        </template>

        <!-- Discussion (stub) -->
        <template v-else-if="activeTab === 'discussion'">
          <div class="rounded-xl border border-gray-200 bg-gray-50 p-8 text-center">
            <UIcon name="i-lucide-message-square" class="w-8 h-8 mx-auto text-gray-300 mb-3" />
            <h2 class="text-sm font-semibold text-gray-700">Discussion threads</h2>
            <p class="text-xs text-gray-500 mt-2 max-w-md mx-auto">
              Per-card + patient-level physician ↔ advocate conversations with <code>@</code>-mentions.
              Ships next sprint alongside the backend discussion endpoints. Comment-on-card is already live
              inside the Clinical Funnel tab.
            </p>
          </div>
        </template>

        <!-- Watchlist (stub) -->
        <template v-else-if="activeTab === 'watchlist'">
          <div class="rounded-xl border border-gray-200 bg-gray-50 p-8 text-center">
            <UIcon name="i-lucide-star" class="w-8 h-8 mx-auto text-gray-300 mb-3" />
            <h2 class="text-sm font-semibold text-gray-700">My Watchlist</h2>
            <p class="text-xs text-gray-500 mt-2 max-w-md mx-auto">
              Physician-curated list of NCTs + PMIDs to monitor outside the protocol-derived watched trials.
              Ships next sprint. Until then, promote a proposal to <strong>Watching</strong> in the Clinical
              Funnel to keep it on your radar.
            </p>
          </div>
        </template>
      </div>
    </div>

    <!-- #381: trial proposals + literature feed are clinical recommendations — cite sources + disclaimer -->
    <ClinicalSourceFooter
      :sources="[
        { label: 'PubMed', url: 'https://pubmed.ncbi.nlm.nih.gov' },
        { label: 'ClinicalTrials.gov', url: 'https://clinicaltrials.gov' },
        { label: 'EU Clinical Trials Register', url: 'https://www.clinicaltrialsregister.eu' },
      ]"
      compact
    />
  </div>
</template>
