<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const refreshKey = ref(0)
const { data: briefings, status: briefingsStatus, error: briefingsError } = fetchApi<{
  briefings: Array<{
    id: number
    title: string
    content: string
    date: string
    tags: string[] | string
    summary?: string
    action_count?: number
  }>
  total: number
  error?: string
}>(() => refreshKey.value ? `/briefings?nocache=${refreshKey.value}` : '/briefings', { lazy: true, server: false })

function refresh() {
  refreshKey.value = Date.now()
}

const { data: autonomous } = fetchApi<{
  enabled: boolean
  daily_cost: number
  jobs?: Array<{ id: string; schedule: string; description: string }>
}>('/autonomous', { lazy: true, server: false })

function extractQuestions(content: string): string[] {
  const lines = content.split('\n')
  const questions: string[] = []
  let inQSection = false
  for (const line of lines) {
    if (line.toLowerCase().includes('questions for oncologist')) {
      inQSection = true
      continue
    }
    if (inQSection && line.startsWith('#')) break
    if (inQSection && line.trim().startsWith('-')) {
      questions.push(line.trim().replace(/^-\s*/, ''))
    }
  }
  return questions
}

const drilldown = useDrilldown()

const allQuestions = computed(() => {
  if (!briefings.value?.briefings) return []
  return briefings.value.briefings
    .flatMap(b => extractQuestions(b.content).map(q => ({ question: q, from: b.title, date: b.date })))
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('briefings.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('briefings.count', { count: briefings?.total ?? 0 }) }}</p>
        <LastUpdated :timestamp="briefings?.last_updated" />
      </div>
      <div class="flex items-center gap-3">
        <div v-if="autonomous" class="flex items-center gap-2 text-xs">
          <UBadge :color="autonomous.enabled ? 'success' : 'neutral'" variant="subtle" size="xs">
            {{ autonomous.enabled ? $t('common.active') : $t('common.disabled') }}
          </UBadge>
          <span v-if="autonomous.daily_cost > 0" class="text-gray-500">
            {{ $t('agents.costToday', { cost: autonomous.daily_cost.toFixed(4) }) }}
          </span>
        </div>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="briefings?.error || briefingsError?.message" />
    <SkeletonLoader v-if="!briefings && briefingsStatus === 'pending'" variant="cards" />
    <div v-else-if="briefingsError || briefings?.error || briefingsStatus === 'error'" class="text-center py-16 space-y-2">
      <UIcon name="i-lucide-wifi-off" class="h-6 w-6 mx-auto text-gray-300" />
      <p class="text-sm text-gray-500">{{ $t('common.dataUnavailable') }}</p>
    </div>

    <!-- Questions for Oncologist (aggregated) -->
    <div v-if="allQuestions.length" class="rounded-xl border border-teal-500/30 bg-teal-500/5 p-4">
      <div class="flex items-center gap-2 mb-3">
        <UIcon name="i-lucide-message-circle-question" class="text-teal-600" />
        <h2 class="text-sm font-semibold text-gray-900">{{ $t('briefings.questionsForOncologist') }}</h2>
      </div>
      <div class="space-y-2">
        <div v-for="(q, i) in allQuestions" :key="i" class="flex items-start gap-2">
          <span class="text-teal-600 text-xs mt-0.5 shrink-0">{{ i + 1 }}.</span>
          <div>
            <div class="text-sm text-gray-700">{{ q.question }}</div>
            <div class="text-xs text-gray-500">{{ q.from }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Briefing Cards -->
    <div v-if="briefings?.briefings?.length" class="space-y-2">
      <BriefingCard
        v-for="b in briefings.briefings"
        :key="b.id"
        :title="b.title"
        :content="b.content"
        :date="b.date"
        :tags="b.tags"
        :summary="b.summary"
        :action-count="b.action_count"
        @drilldown="drilldown.open({ type: 'conversation', id: b.id, label: b.title })"
      />
    </div>

    <div v-else-if="!briefings?.error && !briefingsError && briefingsStatus !== 'pending' && briefingsStatus !== 'error'" class="text-center py-16 space-y-4">
      <div class="text-gray-500 text-sm">
        {{ $t('briefings.noBriefings') }}
      </div>
      <!-- Show scheduled tasks that will generate briefings -->
      <div v-if="autonomous?.jobs?.length" class="inline-flex flex-wrap justify-center gap-2 max-w-lg">
        <div
          v-for="job in autonomous.jobs"
          :key="job.id"
          class="rounded-lg bg-gray-50 px-3 py-1.5 text-xs text-gray-500"
        >
          {{ job.description }} · {{ job.schedule }}
        </div>
      </div>
    </div>
  </div>
</template>
