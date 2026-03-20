<script setup lang="ts">
defineProps<{
  id: string
  rule: string
  source: string
}>()

const severityColor = computed(() => {
  return 'border-amber-500/40 bg-amber-500/10'
})
</script>

<template>
  <div class="rounded-lg border p-3 flex items-start gap-3" :class="severityColor">
    <UIcon name="i-lucide-triangle-alert" class="text-amber-500 shrink-0 mt-0.5" />
    <div class="min-w-0">
      <div class="text-xs font-mono text-gray-500">{{ id }}</div>
      <div class="text-sm text-gray-900">{{ rule }}</div>
      <div class="text-xs text-gray-500 mt-0.5">{{ source }}</div>
    </div>
  </div>
</template>
