<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { getLevel, computeXpFromStats } = useGamification()

const { data: status, refresh: refreshStatus } = await fetchApi<{
  status: string
  version: string
  session_id: string
  tools_count: number
}>('/status')

const { data: stats, refresh: refreshStats } = await fetchApi<{
  stats: Array<{ tool_name: string; status: string; count: number; avg_duration_ms: number }>
}>('/stats')

const { data: activity, refresh: refreshActivity } = await fetchApi<{
  entries: Array<{ tool: string; status: string; duration_ms: number; timestamp: string }>
  total: number
}>('/activity?limit=10')

const totalXp = computed(() => {
  if (!stats.value?.stats) return 0
  return computeXpFromStats(stats.value.stats)
})

const level = computed(() => getLevel(totalXp.value))

const totalCalls = computed(() => {
  if (!stats.value?.stats) return 0
  return stats.value.stats.reduce((sum, s) => sum + s.count, 0)
})

async function refreshAll() {
  await Promise.all([refreshStatus(), refreshStats(), refreshActivity()])
}

// Auto-refresh every 30 seconds
const refreshInterval = ref<ReturnType<typeof setInterval>>()
onMounted(() => {
  refreshInterval.value = setInterval(refreshAll, 30_000)
})
onUnmounted(() => {
  clearInterval(refreshInterval.value)
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" @click="refreshAll" />
    </div>

    <!-- Status + XP bar -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon name="i-lucide-activity" class="text-green-500" />
            <span class="font-semibold">Status</span>
          </div>
        </template>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between">
            <span class="text-muted">Server</span>
            <UBadge :color="status?.status === 'ok' ? 'success' : 'error'" variant="subtle">
              {{ status?.status ?? 'unknown' }}
            </UBadge>
          </div>
          <div class="flex justify-between">
            <span class="text-muted">Version</span>
            <span>{{ status?.version }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted">Session</span>
            <span class="font-mono text-xs">{{ status?.session_id }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted">Tools</span>
            <span>{{ status?.tools_count }}</span>
          </div>
        </div>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon name="i-lucide-trophy" class="text-yellow-500" />
            <span class="font-semibold">Level: {{ level.name }}</span>
          </div>
        </template>
        <div class="space-y-3">
          <div class="text-3xl font-bold text-primary">{{ totalXp }} XP</div>
          <UProgress
            :model-value="level.progress * 100"
            color="primary"
            size="md"
          />
          <div v-if="level.nextLevel" class="text-xs text-muted">
            {{ level.nextMinXp! - totalXp }} XP to {{ level.nextLevel }}
          </div>
          <div v-else class="text-xs text-muted">Max level reached</div>
        </div>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon name="i-lucide-bar-chart-3" class="text-blue-500" />
            <span class="font-semibold">Stats</span>
          </div>
        </template>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between">
            <span class="text-muted">Total calls</span>
            <span class="font-bold">{{ totalCalls }}</span>
          </div>
          <div v-for="s in stats?.stats?.slice(0, 4)" :key="s.tool_name" class="flex justify-between">
            <span class="text-muted truncate mr-2">{{ s.tool_name }}</span>
            <span>{{ s.count }}</span>
          </div>
        </div>
      </UCard>
    </div>

    <!-- Activity feed -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-lucide-scroll-text" />
          <span class="font-semibold">Recent Activity</span>
          <UBadge variant="subtle" size="sm">{{ activity?.total ?? 0 }}</UBadge>
        </div>
      </template>
      <div v-if="activity?.entries?.length" class="divide-y divide-default">
        <div v-for="(entry, i) in activity.entries" :key="i" class="py-2 flex items-center gap-3 text-sm">
          <UIcon
            :name="entry.status === 'ok' ? 'i-lucide-check-circle' : 'i-lucide-x-circle'"
            :class="entry.status === 'ok' ? 'text-green-500' : 'text-red-500'"
          />
          <span class="font-mono text-xs min-w-28">{{ entry.tool }}</span>
          <span v-if="entry.duration_ms" class="text-muted text-xs">{{ entry.duration_ms }}ms</span>
          <span class="text-muted text-xs ml-auto">{{ entry.timestamp?.split('T')[0] }}</span>
        </div>
      </div>
      <div v-else class="text-muted text-sm py-4 text-center">No activity yet</div>
    </UCard>
  </div>
</template>
