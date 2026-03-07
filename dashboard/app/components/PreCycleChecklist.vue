<script setup lang="ts">
defineProps<{
  currentCycle: number
}>()

const sections = [
  {
    title: 'Laboratory Safety',
    items: [
      'ANC >= 1,500/uL',
      'PLT >= 75,000/uL (also check >= 50,000 for full-dose Clexane)',
      'Creatinine <= 1.5x ULN',
      'ALT/AST <= 5x ULN (liver mets threshold)',
      'Bilirubin <= 1.5x ULN',
    ],
  },
  {
    title: 'Toxicity Assessment (NCI-CTC)',
    items: [
      'Peripheral neuropathy grade',
      'Diarrhea grade',
      'Mucositis grade',
      'Fatigue grade',
      'Hand-foot syndrome grade',
      'Nausea/vomiting grade',
    ],
  },
  {
    title: 'VTE Monitoring',
    items: [
      'PLT adequate for Clexane continuation',
      'No new DVT/PE symptoms (leg swelling, dyspnea, chest pain)',
      'Clexane compliance confirmed',
    ],
  },
  {
    title: 'General Assessment',
    items: [
      'ECOG performance status',
      'Weight + change from baseline',
      'Nutritional status adequate',
    ],
  },
]

const checked = ref<Record<string, boolean>>({})
</script>

<template>
  <div class="space-y-4">
    <h3 class="text-sm font-semibold text-white">Pre-Cycle {{ currentCycle }} Checklist - mFOLFOX6</h3>
    <div v-for="section in sections" :key="section.title" class="space-y-2">
      <div class="text-xs font-medium text-gray-400 uppercase tracking-wide">{{ section.title }}</div>
      <div v-for="item in section.items" :key="item" class="flex items-center gap-2">
        <input
          v-model="checked[item]"
          type="checkbox"
          class="rounded border-gray-700 bg-gray-800 text-teal-500 focus:ring-teal-500/30 w-3.5 h-3.5"
        />
        <span class="text-sm text-gray-300" :class="{ 'line-through text-gray-600': checked[item] }">{{ item }}</span>
      </div>
    </div>
  </div>
</template>
