<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const typeFilter = ref<'all' | 'clinical' | 'technical'>('all')

const { data: sessions, status: sessionsStatus, error: sessionsError, refresh } = fetchApi<{
  sessions: Array<{
    id: number
    title: string
    content: string
    date: string | null
    tags: string[] | null
    session_type: 'clinical' | 'technical'
  }>
  total: number
  type_counts: { clinical: number; technical: number }
  error?: string
}>(() => `/sessions?limit=50&type=${typeFilter.value}`, { lazy: true, watch: [typeFilter] })

const drilldown = useDrilldown()

const totalAll = computed(() => {
  const c = sessions.value?.type_counts
  return c ? c.clinical + c.technical : 0
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('sessions.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('sessions.count', { count: sessions?.total ?? 0 }) }}</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <!-- Filter pills -->
    <div class="flex gap-2">
      <UButton
        size="xs"
        :variant="typeFilter === 'all' ? 'solid' : 'ghost'"
        :color="typeFilter === 'all' ? 'primary' : 'neutral'"
        @click="typeFilter = 'all'"
      >
        {{ $t('sessions.filterAll') }} ({{ totalAll }})
      </UButton>
      <UButton
        size="xs"
        :variant="typeFilter === 'clinical' ? 'solid' : 'ghost'"
        :color="typeFilter === 'clinical' ? 'primary' : 'neutral'"
        @click="typeFilter = 'clinical'"
      >
        {{ $t('sessions.filterClinical') }} ({{ sessions?.type_counts?.clinical ?? 0 }})
      </UButton>
      <UButton
        size="xs"
        :variant="typeFilter === 'technical' ? 'solid' : 'ghost'"
        :color="typeFilter === 'technical' ? 'primary' : 'neutral'"
        @click="typeFilter = 'technical'"
      >
        {{ $t('sessions.filterTechnical') }} ({{ sessions?.type_counts?.technical ?? 0 }})
      </UButton>
    </div>

    <ApiErrorBanner :error="sessions?.error || sessionsError?.message" />
    <SkeletonLoader v-if="!sessions && sessionsStatus === 'pending'" variant="cards" />

    <div v-else-if="sessions?.sessions?.length" class="space-y-3">
      <div
        v-for="session in sessions.sessions"
        :key="session.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 overflow-hidden cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="drilldown.open({ type: 'conversation', id: session.id, label: session.title })"
      >
        <div class="px-4 py-3 border-b border-gray-800/50 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="font-medium text-white text-sm">{{ session.title }}</span>
            <UBadge
              size="xs"
              variant="subtle"
              :color="session.session_type === 'clinical' ? 'success' : 'neutral'"
            >
              {{ session.session_type === 'clinical' ? $t('sessions.typeClinical') : $t('sessions.typeTechnical') }}
            </UBadge>
          </div>
          <span v-if="session.date" class="text-xs text-gray-500">
            {{ formatDate(session.date.split('T')[0]) }}
          </span>
        </div>
        <div class="px-4 py-3">
          <p class="text-sm text-gray-400 whitespace-pre-line">{{ session.content }}</p>
        </div>
        <div v-if="session.tags?.length" class="px-4 py-2 border-t border-gray-800/50 flex gap-1 flex-wrap">
          <UBadge v-for="tag in session.tags" :key="tag" variant="subtle" size="xs" color="neutral">
            {{ tag }}
          </UBadge>
        </div>
      </div>
    </div>

    <div v-else-if="!sessions?.error && !sessionsError" class="text-gray-600 text-center py-16 text-sm">
      {{ $t('sessions.noSessions') }}
    </div>
  </div>
</template>
