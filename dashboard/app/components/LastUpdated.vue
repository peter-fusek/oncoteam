<script setup lang="ts">
const props = defineProps<{ timestamp?: string | null }>()
const { timeAgo: formatTimeAgo } = useAgentFormatters()

const label = computed(() => {
  if (!props.timestamp) return null
  return formatTimeAgo(props.timestamp)
})
</script>

<template>
  <span v-if="label" class="text-[10px] text-gray-500">
    Last updated: {{ label }}
  </span>
</template>
