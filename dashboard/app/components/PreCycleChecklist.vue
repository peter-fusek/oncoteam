<script setup lang="ts">
defineProps<{
  currentCycle: number
}>()

const { t } = useI18n()

const sections = computed(() => [
  {
    title: t('components.checklist.sections.labSafety'),
    items: [
      t('components.checklist.labItems.anc'),
      t('components.checklist.labItems.plt'),
      t('components.checklist.labItems.creatinine'),
      t('components.checklist.labItems.altAst'),
      t('components.checklist.labItems.bilirubin'),
    ],
  },
  {
    title: t('components.checklist.sections.toxicityAssessment'),
    items: [
      t('components.checklist.toxItems.neuropathy'),
      t('components.checklist.toxItems.diarrhea'),
      t('components.checklist.toxItems.mucositis'),
      t('components.checklist.toxItems.fatigue'),
      t('components.checklist.toxItems.handFoot'),
      t('components.checklist.toxItems.nausea'),
    ],
  },
  {
    title: t('components.checklist.sections.vteMonitoring'),
    items: [
      t('components.checklist.vteItems.pltClexane'),
      t('components.checklist.vteItems.noDvt'),
      t('components.checklist.vteItems.clexaneCompliance'),
    ],
  },
  {
    title: t('components.checklist.sections.generalAssessment'),
    items: [
      t('components.checklist.generalItems.ecog'),
      t('components.checklist.generalItems.weight'),
      t('components.checklist.generalItems.nutritional'),
    ],
  },
])

const checked = ref<Record<string, boolean>>({})
</script>

<template>
  <div class="space-y-4">
    <h3 class="text-sm font-semibold text-white">{{ $t('components.checklist.title', { cycle: currentCycle }) }} - mFOLFOX6</h3>
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
