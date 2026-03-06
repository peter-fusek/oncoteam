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
      <h1 class="text-2xl font-bold">Session History</h1>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" @click="refresh" />
    </div>

    <div v-if="sessions?.sessions?.length" class="space-y-4">
      <UCard v-for="session in sessions.sessions" :key="session.id">
        <template #header>
          <div class="flex items-center justify-between">
            <span class="font-medium">{{ session.title }}</span>
            <span v-if="session.date" class="text-xs text-muted">{{ session.date.split('T')[0] }}</span>
          </div>
        </template>
        <p class="text-sm whitespace-pre-line">{{ session.content }}</p>
        <template v-if="session.tags?.length" #footer>
          <div class="flex gap-1 flex-wrap">
            <UBadge v-for="tag in session.tags" :key="tag" variant="subtle" size="xs">
              {{ tag }}
            </UBadge>
          </div>
        </template>
      </UCard>
    </div>

    <div v-else class="text-muted text-center py-12">
      No session summaries yet
    </div>
  </div>
</template>
