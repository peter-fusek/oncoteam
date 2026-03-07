<script setup lang="ts">
const props = defineProps<{
  milestones: Array<{ cycle: number; action: string; description: string }>
  currentCycle: number
}>()

function milestoneStatus(cycle: number) {
  if (cycle < props.currentCycle) return 'done'
  if (cycle === props.currentCycle || cycle === props.currentCycle + 1) return 'upcoming'
  return 'future'
}

function statusColor(status: string) {
  switch (status) {
    case 'done': return 'bg-green-500'
    case 'upcoming': return 'bg-amber-500'
    default: return 'bg-gray-600'
  }
}
</script>

<template>
  <div class="space-y-3">
    <div
      v-for="m in milestones"
      :key="m.action"
      class="flex items-start gap-3"
    >
      <div class="flex flex-col items-center">
        <div class="w-3 h-3 rounded-full" :class="statusColor(milestoneStatus(m.cycle))" />
        <div class="w-px h-full bg-gray-800 mt-1" />
      </div>
      <div class="pb-4">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium text-white">Cycle {{ m.cycle }}</span>
          <UBadge
            :color="milestoneStatus(m.cycle) === 'done' ? 'success' : milestoneStatus(m.cycle) === 'upcoming' ? 'warning' : 'neutral'"
            variant="subtle"
            size="xs"
          >
            {{ milestoneStatus(m.cycle) }}
          </UBadge>
        </div>
        <div class="text-xs text-gray-400 mt-0.5">{{ m.description }}</div>
        <div class="text-xs text-gray-600 font-mono">{{ m.action }}</div>
      </div>
    </div>
  </div>
</template>
