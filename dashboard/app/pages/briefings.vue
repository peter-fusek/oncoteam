<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: briefings, refresh } = await fetchApi<{
  briefings: Array<{
    id: number
    title: string
    content: string
    date: string
    tags: string[] | string
  }>
  total: number
  error?: string
}>('/briefings')

const { data: autonomous } = await fetchApi<{
  enabled: boolean
  daily_cost: number
  jobs?: Array<{ id: string; schedule: string; description: string }>
}>('/autonomous')

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
        <h1 class="text-2xl font-bold text-white">{{ $t('briefings.title') }}</h1>
        <p class="text-sm text-gray-400">{{ briefings?.total ?? 0 }} briefings</p>
      </div>
      <div class="flex items-center gap-3">
        <div v-if="autonomous" class="flex items-center gap-2 text-xs">
          <UBadge :color="autonomous.enabled ? 'success' : 'neutral'" variant="subtle" size="xs">
            {{ autonomous.enabled ? 'Active' : 'Disabled' }}
          </UBadge>
          <span v-if="autonomous.daily_cost > 0" class="text-gray-500">
            ${{ autonomous.daily_cost.toFixed(4) }} today
          </span>
        </div>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="briefings?.error" />

    <!-- Questions for Oncologist (aggregated) -->
    <div v-if="allQuestions.length" class="rounded-xl border border-teal-500/30 bg-teal-500/5 p-4">
      <div class="flex items-center gap-2 mb-3">
        <UIcon name="i-lucide-message-circle-question" class="text-teal-500" />
        <h2 class="text-sm font-semibold text-white">Questions for Oncologist</h2>
      </div>
      <div class="space-y-2">
        <div v-for="(q, i) in allQuestions" :key="i" class="flex items-start gap-2">
          <span class="text-teal-500 text-xs mt-0.5 shrink-0">{{ i + 1 }}.</span>
          <div>
            <div class="text-sm text-gray-300">{{ q.question }}</div>
            <div class="text-xs text-gray-600">{{ q.from }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Task Schedule -->
    <div v-if="autonomous?.jobs?.length" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <h2 class="text-sm font-semibold text-white mb-3">Scheduled Tasks</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div v-for="job in autonomous.jobs" :key="job.id" class="rounded-lg bg-gray-800/50 px-3 py-2">
          <div class="text-xs font-mono text-gray-300">{{ job.id }}</div>
          <div class="text-xs text-gray-500">{{ job.schedule }}</div>
          <div class="text-xs text-gray-600 mt-0.5">{{ job.description }}</div>
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
        @drilldown="drilldown.open({ type: 'conversation', id: b.id, label: b.title })"
      />
    </div>

    <div v-else-if="!briefings?.error" class="text-gray-600 text-center py-16 text-sm">
      {{ $t('briefings.noBriefings') }}
    </div>
  </div>
</template>
