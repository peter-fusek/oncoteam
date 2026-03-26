<script setup lang="ts">
import type { FunnelStage, FunnelAssessment } from '~/composables/useFunnelStage'

interface ResearchEntry {
  id: number
  source: string
  external_id: string
  title: string
  summary: string
  date: string | null
  external_url: string | null
  relevance: string
  relevance_reason: string
}

const props = defineProps<{
  trial: ResearchEntry
  assessment: FunnelAssessment | null
  isAssessing: boolean
  isWatched?: boolean
}>()

const emit = defineEmits<{
  move: [stage: FunnelStage]
  click: []
  toggleActive: []
}>()

const isActive = computed(() => props.assessment?.active !== false)

const { FUNNEL_STAGES } = useFunnelStage()

const relevanceColors: Record<string, string> = {
  high: 'success',
  medium: 'info',
  low: 'neutral',
  not_applicable: 'error',
}

const stageItems = computed(() =>
  FUNNEL_STAGES.filter(s => s !== props.assessment?.stage).map(s => ({
    label: s,
    click: () => emit('move', s),
  })),
)
</script>

<template>
  <div
    class="rounded-xl border border-gray-200 bg-white p-3 hover:shadow-sm transition-all cursor-pointer"
    :class="{ 'opacity-50': isAssessing, 'opacity-40 grayscale': !isActive }"
    @click="emit('click')"
  >
    <!-- Header: NCT ID + relevance + move menu -->
    <div class="flex items-center justify-between gap-2 mb-1.5">
      <code class="text-[10px] text-teal-700 font-mono">{{ trial.external_id }}</code>
      <div class="flex items-center gap-1">
        <UBadge variant="subtle" size="xs" :color="relevanceColors[trial.relevance] || 'neutral'">
          {{ trial.relevance }}
        </UBadge>
        <UButton
          :icon="isActive ? 'i-lucide-eye' : 'i-lucide-eye-off'"
          variant="ghost"
          size="xs"
          :color="isActive ? 'neutral' : 'warning'"
          :title="isActive ? 'Mark as passive' : 'Mark as active'"
          @click.stop="emit('toggleActive')"
        />
        <UDropdownMenu
          :items="stageItems"
          :popper="{ placement: 'bottom-end' }"
          @click.stop
        >
          <UButton icon="i-lucide-move" variant="ghost" size="xs" color="neutral" @click.stop />
        </UDropdownMenu>
      </div>
    </div>

    <!-- Watched badge -->
    <div v-if="isWatched" class="flex items-center gap-1 mb-1">
      <UBadge variant="subtle" size="xs" color="primary">
        <UIcon name="i-lucide-bookmark" class="w-2.5 h-2.5 mr-0.5" />
        Monitored
      </UBadge>
    </div>

    <!-- Title -->
    <p class="text-sm font-medium text-gray-900 line-clamp-2 mb-1.5">{{ trial.title }}</p>

    <!-- Exclusion reason -->
    <p v-if="assessment?.exclusion_reason" class="text-xs text-red-600 italic mb-1">
      {{ assessment.exclusion_reason }}
    </p>

    <!-- Next step -->
    <div v-if="assessment?.next_step" class="flex items-start gap-1.5 text-xs text-gray-600 mb-1">
      <UIcon name="i-lucide-arrow-right" class="w-3 h-3 mt-0.5 shrink-0 text-gray-400" />
      <span>{{ assessment.next_step }}</span>
    </div>

    <!-- Deadline -->
    <div v-if="assessment?.deadline_note" class="flex items-start gap-1.5 text-xs text-amber-600">
      <UIcon name="i-lucide-clock" class="w-3 h-3 mt-0.5 shrink-0" />
      <span>{{ assessment.deadline_note }}</span>
    </div>

    <!-- Assessing spinner -->
    <div v-if="isAssessing" class="flex items-center gap-1.5 text-xs text-gray-400 mt-1">
      <UIcon name="i-lucide-loader-2" class="w-3 h-3 animate-spin" />
      Assessing...
    </div>
  </div>
</template>
