<script setup lang="ts">
const props = defineProps<{
  name: string
  value: string
  implication?: string
  // #398 Phase 3a — source traceability derived from oncopanel.
  // Present when this biomarker is backed by a structured variant/CNV entry;
  // absent for flat-dict-only data (legacy patients, IHC-only reports, etc.).
  source?: string                // e.g. "oncopanel · 2026-04-18"
  sourceLab?: string             // e.g. "OUSA — Ústav sv. Alžbety"
  sourceDocId?: string           // oncofiles document ID for drill-through
  variantDetail?: string         // e.g. "G12S · VAF 12.8% · IA"
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
      <NuxtLink :to="`/dictionary?q=${name}`" class="font-semibold text-sm text-gray-900 underline decoration-dotted decoration-gray-400 hover:decoration-green-600 hover:text-green-700 transition-colors" @click.stop :title="`Look up ${name} in dictionary`">{{ name }}</NuxtLink>
      <span class="w-2 h-2 rounded-full" :class="colors.dot" />
    </div>
    <div class="text-xs text-gray-700">{{ value }}</div>
    <div v-if="implication" class="text-xs text-gray-500 mt-1 italic">{{ implication }}</div>
    <!-- #398 Phase 3a source chip — shown only when oncopanel-backed. Click
         stops propagation so the user drills into the source doc instead of
         the biomarker panel. -->
    <div v-if="source" class="mt-2 pt-2 border-t border-gray-200/60 flex items-center gap-1.5 text-[10px] text-gray-500">
      <UIcon name="i-lucide-dna" class="w-3 h-3 text-gray-400 shrink-0" />
      <span class="italic">{{ source }}</span>
      <span v-if="variantDetail" class="text-gray-400">· {{ variantDetail }}</span>
      <span v-if="sourceLab" class="text-gray-400 truncate">· {{ sourceLab }}</span>
    </div>
  </div>
</template>
