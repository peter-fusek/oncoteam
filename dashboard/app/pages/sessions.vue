<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const { data: sessions, status: sessionsStatus, refresh } = fetchApi<{
  sessions: Array<{
    id: number
    title: string
    content: string
    date: string | null
    tags: string[] | null
  }>
  total: number
  error?: string
}>('/sessions?limit=50', { lazy: true })

const drilldown = useDrilldown()
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

    <ApiErrorBanner :error="sessions?.error" />
    <SkeletonLoader v-if="!sessions && sessionsStatus === 'pending'" variant="cards" />

    <div v-else-if="sessions?.sessions?.length" class="space-y-3">
      <div
        v-for="session in sessions.sessions"
        :key="session.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 overflow-hidden cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="drilldown.open({ type: 'conversation', id: session.id, label: session.title })"
      >
        <div class="px-4 py-3 border-b border-gray-800/50 flex items-center justify-between">
          <span class="font-medium text-white text-sm">{{ session.title }}</span>
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

    <div v-else-if="!sessions?.error" class="text-gray-600 text-center py-16 text-sm">
      {{ $t('sessions.noSessions') }}
    </div>
  </div>
</template>
