<script setup lang="ts">
const props = defineProps<{ timestamp?: string | null }>()

const timeAgo = computed(() => {
  if (!props.timestamp) return null
  const diff = Date.now() - new Date(props.timestamp).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
})
</script>

<template>
  <span v-if="timeAgo" class="text-[10px] text-gray-500">
    Last updated: {{ timeAgo }}
  </span>
</template>
