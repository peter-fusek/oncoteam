<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: timeline, refresh } = await fetchApi<{
  events: Array<{
    id: number
    date: string
    type: string
    title: string
    notes: string
  }>
  total: number
}>('/timeline')

const typeEmoji: Record<string, string> = {
  chemo_cycle: '💊',
  chemo: '💊',
  lab_work: '🧪',
  consultation: '🩺',
  surgery: '🔪',
  scan: '📡',
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Treatment Timeline</h1>
        <p class="text-sm text-gray-400">{{ timeline?.total ?? 0 }} events</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <div v-if="timeline?.events?.length" class="relative pl-6">
      <!-- Vertical line -->
      <div class="absolute left-2 top-2 bottom-2 w-px bg-gray-800" />

      <div v-for="event in timeline.events" :key="event.id" class="relative pb-6 last:pb-0">
        <!-- Dot -->
        <div class="absolute -left-4 top-3 w-3 h-3 rounded-full border-2 border-gray-700 bg-gray-900" />

        <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-4">
          <div class="flex items-start gap-3">
            <span class="text-lg">{{ typeEmoji[event.type] ?? '📅' }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-white text-sm">{{ event.title }}</span>
                <UBadge variant="subtle" size="xs" color="neutral">{{ event.type }}</UBadge>
              </div>
              <div class="text-xs text-gray-500 mt-1">{{ event.date }}</div>
              <p v-if="event.notes" class="text-xs text-gray-400 mt-2">{{ event.notes }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="text-gray-600 text-center py-16 text-sm">
      No treatment events
    </div>
  </div>
</template>
