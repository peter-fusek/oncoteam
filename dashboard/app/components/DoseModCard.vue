<script setup lang="ts">
defineProps<{
  toxicity: string
  action: string
  source?: string
  sourceUrl?: string
}>()

function formatToxicity(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white p-3">
    <div class="text-sm font-medium text-gray-900">{{ formatToxicity(toxicity) }}</div>
    <div class="text-xs text-gray-500 mt-1">{{ action }}</div>
    <div v-if="sourceUrl" class="mt-1">
      <a :href="sourceUrl" target="_blank" rel="noopener" class="text-[10px] text-teal-600 hover:underline" @click.stop>{{ source }}</a>
    </div>
  </div>
</template>
