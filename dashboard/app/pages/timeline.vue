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

const typeColors: Record<string, string> = {
  chemo_cycle: 'text-purple-500',
  chemo: 'text-purple-500',
  lab_work: 'text-blue-500',
  consultation: 'text-green-500',
  surgery: 'text-red-500',
  scan: 'text-yellow-500',
}

const typeIcons: Record<string, string> = {
  chemo_cycle: 'i-lucide-pill',
  chemo: 'i-lucide-pill',
  lab_work: 'i-lucide-test-tube',
  consultation: 'i-lucide-stethoscope',
  surgery: 'i-lucide-scissors',
  scan: 'i-lucide-scan',
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Treatment Timeline</h1>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" @click="refresh" />
    </div>

    <div v-if="timeline?.events?.length" class="relative">
      <!-- Vertical line -->
      <div class="absolute left-4 top-0 bottom-0 w-px bg-default" />

      <div v-for="event in timeline.events" :key="event.id" class="relative pl-10 pb-6">
        <!-- Dot on the line -->
        <div class="absolute left-2.5 top-1 size-3 rounded-full bg-default ring-2 ring-default" />

        <UCard>
          <div class="flex items-start gap-3">
            <UIcon
              :name="typeIcons[event.type] ?? 'i-lucide-calendar'"
              :class="typeColors[event.type] ?? 'text-muted'"
              class="mt-0.5 shrink-0"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="font-medium">{{ event.title }}</span>
                <UBadge variant="subtle" size="xs">{{ event.type }}</UBadge>
              </div>
              <div class="text-xs text-muted mt-1">{{ event.date }}</div>
              <p v-if="event.notes" class="text-sm text-muted mt-2">
                {{ event.notes }}
              </p>
            </div>
          </div>
        </UCard>
      </div>
    </div>

    <div v-else class="text-muted text-center py-12">
      No treatment events
    </div>
  </div>
</template>
