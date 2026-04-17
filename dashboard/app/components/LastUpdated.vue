<script setup lang="ts">
const props = defineProps<{ timestamp?: string | null }>()
const { timeAgo: formatTimeAgo } = useAgentFormatters()

// Tick every 10s so "N seconds ago" stays honest without a data refetch.
const tick = ref(0)
if (import.meta.client) {
  const id = setInterval(() => { tick.value++ }, 10_000)
  onBeforeUnmount(() => clearInterval(id))
}

const label = computed(() => {
  // Touch tick to force recompute; formatTimeAgo reads the current clock.
  void tick.value
  if (!props.timestamp) return null
  return formatTimeAgo(props.timestamp)
})
</script>

<template>
  <span v-if="label" class="text-[10px] text-gray-500">
    Last updated: {{ label }}
  </span>
</template>
