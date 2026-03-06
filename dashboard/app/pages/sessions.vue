<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: sessions, refresh } = await fetchApi<{
  sessions: Array<{
    id: number
    title: string
    content: string
    date: string | null
    tags: string[] | null
  }>
  total: number
}>('/sessions?limit=50')
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Session History</h1>
        <p class="text-sm text-gray-400">{{ sessions?.total ?? 0 }} sessions logged</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <div v-if="sessions?.sessions?.length" class="space-y-3">
      <div
        v-for="session in sessions.sessions"
        :key="session.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 overflow-hidden"
      >
        <div class="px-4 py-3 border-b border-gray-800/50 flex items-center justify-between">
          <span class="font-medium text-white text-sm">{{ session.title }}</span>
          <span v-if="session.date" class="text-xs text-gray-500">
            {{ session.date.split('T')[0] }}
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

    <div v-else class="text-gray-600 text-center py-16 text-sm">
      No session summaries yet
    </div>
  </div>
</template>
