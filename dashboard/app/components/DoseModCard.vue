<script setup lang="ts">
defineProps<{
  toxicity: string
  action: string
}>()

function formatToxicity(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
</script>

<template>
  <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
    <div class="text-sm font-medium text-white">{{ formatToxicity(toxicity) }}</div>
    <div class="text-xs text-gray-400 mt-1">{{ action }}</div>
  </div>
</template>
