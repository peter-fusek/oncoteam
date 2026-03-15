<script setup lang="ts">
const props = defineProps<{
  currentCycle: number
  labValues?: Record<string, { value: number; threshold: number | null; unit: string; pass: boolean }>
  lastLabValues?: Record<string, { value: number; sample_date?: string; status: 'safe' | 'warning' | 'critical' }>
  labThresholds?: Record<string, { min?: number; max_ratio?: number; unit?: string }>
  readonly?: boolean
}>()

const { t } = useI18n()

// Lab safety items mapped to threshold keys for evaluation mode
const labItems = computed(() => [
  { key: 'ANC', label: t('components.checklist.labItems.anc') },
  { key: 'PLT', label: t('components.checklist.labItems.plt') },
  { key: 'creatinine', label: t('components.checklist.labItems.creatinine') },
  { key: 'ALT', label: t('components.checklist.labItems.altAst') },
  { key: 'bilirubin', label: t('components.checklist.labItems.bilirubin') },
])

const sections = computed(() => [
  {
    title: t('components.checklist.sections.labSafety'),
    items: labItems.value.map(i => i.label),
    labKeys: labItems.value.map(i => i.key),
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

function getLabEval(sectionIndex: number, itemIndex: number) {
  if (!props.labValues || sectionIndex !== 0) return null
  const key = sections.value[0].labKeys?.[itemIndex]
  return key ? props.labValues[key] ?? null : null
}

function getLastLabInfo(sectionIndex: number, itemIndex: number) {
  if (!props.lastLabValues || sectionIndex !== 0) return null
  const key = sections.value[0].labKeys?.[itemIndex]
  if (!key) return null
  const entry = props.lastLabValues[key]
  if (!entry) return null
  const unit = props.labThresholds?.[key]?.unit ?? ''
  return { ...entry, unit }
}

const statusColor: Record<string, string> = {
  safe: 'text-green-400',
  warning: 'text-amber-400',
  critical: 'text-red-400',
}

const statusIcon: Record<string, string> = {
  safe: 'i-lucide-check-circle',
  warning: 'i-lucide-alert-triangle',
  critical: 'i-lucide-x-circle',
}
</script>

<template>
  <div class="space-y-4">
    <h3 class="text-sm font-semibold text-white">{{ $t('components.checklist.title', { cycle: currentCycle }) }} - mFOLFOX6</h3>
    <div v-for="(section, si) in sections" :key="section.title" class="space-y-2">
      <div class="text-xs font-medium text-gray-400 uppercase tracking-wide">{{ section.title }}</div>
      <div v-for="(item, ii) in section.items" :key="item" class="flex items-center gap-2">
        <!-- Evaluation mode: show actual values -->
        <template v-if="readonly && labValues">
          <template v-if="getLabEval(si, ii)">
            <UIcon
              :name="getLabEval(si, ii)!.pass ? 'i-lucide-check-circle' : 'i-lucide-x-circle'"
              :class="getLabEval(si, ii)!.pass ? 'text-green-500' : 'text-red-500'"
              class="w-4 h-4 shrink-0"
            />
            <span class="text-sm" :class="getLabEval(si, ii)!.pass ? 'text-gray-300' : 'text-red-400'">
              {{ item }}
              <span class="ml-1 font-mono text-xs">
                ({{ getLabEval(si, ii)!.value }}{{ getLabEval(si, ii)!.unit ? ' ' + getLabEval(si, ii)!.unit : '' }})
              </span>
            </span>
          </template>
          <template v-else>
            <UIcon name="i-lucide-minus" class="text-gray-600 w-4 h-4 shrink-0" />
            <span class="text-sm text-gray-600">{{ item }}</span>
          </template>
        </template>
        <!-- Normal checkbox mode -->
        <template v-else>
          <input
            v-model="checked[item]"
            type="checkbox"
            class="rounded border-gray-700 bg-gray-800 text-teal-500 focus:ring-teal-500/30 w-3.5 h-3.5"
          />
          <span class="text-sm text-gray-300 flex-1" :class="{ 'line-through text-gray-600': checked[item] }">{{ item }}</span>
          <!-- Show latest lab value inline when available -->
          <template v-if="getLastLabInfo(si, ii)">
            <UIcon
              :name="statusIcon[getLastLabInfo(si, ii)!.status] ?? 'i-lucide-minus'"
              :class="statusColor[getLastLabInfo(si, ii)!.status] ?? 'text-gray-500'"
              class="w-3.5 h-3.5 shrink-0"
            />
            <span class="font-mono text-xs shrink-0" :class="statusColor[getLastLabInfo(si, ii)!.status] ?? 'text-gray-500'">
              {{ getLastLabInfo(si, ii)!.value }}{{ getLastLabInfo(si, ii)!.unit ? ' ' + getLastLabInfo(si, ii)!.unit : '' }}
            </span>
            <span v-if="getLastLabInfo(si, ii)!.sample_date" class="text-xs text-gray-600 shrink-0">
              {{ getLastLabInfo(si, ii)!.sample_date }}
            </span>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>
