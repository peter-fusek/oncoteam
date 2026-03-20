<script setup lang="ts">
const props = defineProps<{
  name: string
  value: string
  implication?: string
}>()

defineEmits<{ drilldown: [] }>()

const status = computed(() => {
  const v = props.value.toLowerCase()
  if (v.includes('mutant') || v.includes('positive')) return 'mutant'
  if (v.includes('wild') || v.includes('negative') || v === 'false') return 'wildtype'
  if (v.includes('pmm') || v.includes('mss') || v.includes('stable') || v.includes('proficient')) return 'wildtype'
  return 'unknown'
})

const colors = computed(() => {
  switch (status.value) {
    case 'mutant': return { bg: 'bg-red-500/10', border: 'border-red-500/40', badge: 'error' as const, dot: 'bg-red-500' }
    case 'wildtype': return { bg: 'bg-green-500/10', border: 'border-green-500/40', badge: 'success' as const, dot: 'bg-green-500' }
    default: return { bg: 'bg-gray-500/10', border: 'border-gray-500/40', badge: 'neutral' as const, dot: 'bg-gray-500' }
  }
})
</script>

<template>
  <div
    class="rounded-lg border p-3 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
    :class="[colors.bg, colors.border]"
    @click="$emit('drilldown')"
  >
    <div class="flex items-center justify-between mb-1">
      <span class="font-semibold text-sm text-gray-900">{{ name }}</span>
      <span class="w-2 h-2 rounded-full" :class="colors.dot" />
    </div>
    <div class="text-xs text-gray-700">{{ value }}</div>
    <div v-if="implication" class="text-xs text-gray-500 mt-1 italic">{{ implication }}</div>
  </div>
</template>
