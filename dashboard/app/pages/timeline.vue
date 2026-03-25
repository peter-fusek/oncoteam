<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const { data: timeline, status: timelineStatus, error: timelineError, refresh } = fetchApi<{
  events: Array<{
    id: number
    event_date: string
    event_type: string
    title: string
    notes: string
  }>
  total: number
  error?: string
}>('/timeline', { lazy: true, server: false })

const { data: protocol } = fetchApi<{
  milestones: Array<{ cycle: number; action: string; description: string }>
  current_cycle: number
}>('/protocol', { lazy: true, server: false })

const typeEmoji: Record<string, string> = {
  chemo_cycle: '💊',
  chemo: '💊',
  lab_work: '🧪',
  consultation: '🩺',
  surgery: '🔪',
  scan: '📡',
}

function dotColor(type: string) {
  switch (type) {
    case 'chemo_cycle':
    case 'chemo': return 'border-blue-500 bg-blue-500/20'
    case 'lab_work': return 'border-green-500 bg-green-500/20'
    case 'surgery': return 'border-red-500 bg-red-500/20'
    case 'consultation': return 'border-purple-500 bg-purple-500/20'
    case 'scan': return 'border-cyan-500 bg-cyan-500/20'
    default: return 'border-gray-300 bg-white'
  }
}

// Extract cycle number from title
function getCycleNumber(title: string): number | null {
  const match = title.match(/C(\d+)/i)
  return match ? parseInt(match[1]) : null
}

function getMilestonesForEvent(title: string) {
  if (!protocol.value?.milestones) return []
  const cycle = getCycleNumber(title)
  if (!cycle) return []
  return protocol.value.milestones.filter(m => m.cycle === cycle || m.cycle === cycle + 1)
}

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('timeline.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('timeline.count', { count: timeline?.total ?? 0 }) }}</p>
        <LastUpdated :timestamp="timeline?.last_updated" />
      </div>
      <div class="flex items-center gap-2">
        <UBadge v-if="protocol?.current_cycle" variant="subtle" color="info" size="xs">
          {{ $t('timeline.currentCycle', { n: protocol.current_cycle }) }}
        </UBadge>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <!-- Milestone Summary -->
    <div v-if="protocol?.milestones" class="rounded-xl border border-gray-200 bg-white p-4">
      <div class="flex items-center gap-2 mb-3">
        <UIcon name="i-lucide-milestone" class="text-amber-500" />
        <span class="text-sm font-semibold text-gray-900">{{ $t('timeline.treatmentMilestones') }}</span>
      </div>
      <div class="flex gap-4 overflow-x-auto pb-2">
        <div
          v-for="m in protocol.milestones"
          :key="m.action"
          class="shrink-0 rounded-lg px-3 py-2 text-xs border cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
          :class="m.cycle < protocol.current_cycle
            ? 'border-green-500/30 bg-green-500/5 text-emerald-600'
            : m.cycle <= protocol.current_cycle + 1
              ? 'border-amber-500/30 bg-amber-500/5 text-amber-600'
              : 'border-gray-200 bg-gray-50 text-gray-500'"
          @click="drilldown.open({ type: 'protocol_section', id: `milestone-${m.action}`, label: m.description, data: { cycle: m.cycle, action: m.action, description: m.description, source: 'mFOLFOX6 treatment milestones' } })"
        >
          <div class="font-medium">C{{ m.cycle }}</div>
          <div class="text-[10px] mt-0.5 max-w-32 truncate">{{ m.description }}</div>
        </div>
      </div>
    </div>

    <ApiErrorBanner :error="timeline?.error || timelineError?.message" />
    <SkeletonLoader v-if="!timeline && timelineStatus === 'pending'" variant="cards" />

    <div v-else-if="timeline?.events?.length" class="relative pl-6">
      <!-- Vertical line -->
      <div class="absolute left-2 top-2 bottom-2 w-px bg-gray-100" />

      <div v-for="event in timeline.events" :key="event.id" class="relative pb-6 last:pb-0">
        <!-- Dot -->
        <div class="absolute -left-4 top-3 w-3 h-3 rounded-full border-2" :class="dotColor(event.event_type)" />

        <div
          class="rounded-lg border border-gray-200 bg-white p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
          @click="drilldown.open({ type: 'treatment_event', id: event.id, label: event.title })"
        >
          <div class="flex items-start gap-3">
            <span class="text-lg">{{ typeEmoji[event.event_type] ?? '📅' }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-gray-900 text-sm">{{ event.title }}</span>
                <UBadge variant="subtle" size="xs" color="neutral">{{ $t(`timeline.eventTypes.${event.event_type}`, event.event_type) }}</UBadge>
                <UBadge v-if="getCycleNumber(event.title)" variant="subtle" size="xs" color="info">
                  {{ $t('timeline.cycleBadge', { n: getCycleNumber(event.title) }) }}
                </UBadge>
              </div>
              <div class="text-xs text-gray-500 mt-1">{{ formatDate(event.event_date) }}</div>
              <p v-if="event.notes" class="text-xs text-gray-500 mt-2">{{ event.notes }}</p>

              <!-- Milestone callouts -->
              <div v-if="getMilestonesForEvent(event.title).length" class="mt-2 space-y-1">
                <div
                  v-for="m in getMilestonesForEvent(event.title)"
                  :key="m.action"
                  class="flex items-center gap-1.5 text-xs text-amber-600 cursor-pointer hover:text-amber-600 transition-colors"
                  @click.stop="drilldown.open({ type: 'protocol_section', id: `milestone-${m.action}`, label: m.description, data: { cycle: m.cycle, action: m.action, description: m.description, source: 'mFOLFOX6 treatment milestones' } })"
                >
                  <UIcon name="i-lucide-milestone" class="w-3 h-3" />
                  <span>{{ m.description }}</span>
                  <UIcon name="i-lucide-chevron-right" class="w-2.5 h-2.5" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!timeline?.error && !timelineError" class="text-gray-500 text-center py-16 text-sm">
      {{ $t('timeline.noEvents') }}
    </div>
  </div>
</template>
