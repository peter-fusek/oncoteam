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
  trials: ResearchEntry[]
  watchedTrials?: string[]
}>()

// Match watched trial names against funnel entries (fuzzy: check if trial title contains watched name)
function isWatched(trial: ResearchEntry): boolean {
  if (!props.watchedTrials?.length) return false
  const titleLower = trial.title.toLowerCase()
  return props.watchedTrials.some(w => {
    // Extract key trial name from watched string (e.g. "HARMONi-GI3 (ivonescimab + FOLFOX)" → "harmoni-gi3")
    const nameMatch = w.match(/^([^(]+)/)
    const name = (nameMatch?.[1] || w).trim().toLowerCase()
    return titleLower.includes(name) || name.includes(trial.external_id?.toLowerCase() || '---')
  })
}

const { activeRole } = useUserRole()
const { getStage, setStage, moveStage, toggleActive, clearAll, getAllStages, getLog, loadFromServer, saveToServer, FUNNEL_STAGES } = useFunnelStage()
const showLog = ref(false)
const drilldown = useDrilldown()

const assessingIds = ref<Set<string>>(new Set())
const assessError = ref<string | null>(null)
const stageVersion = ref(0) // trigger reactivity on localStorage changes

const COLUMN_STYLES: Record<FunnelStage, { border: string; bg: string; icon: string }> = {
  'Excluded': { border: 'border-red-200', bg: 'bg-red-50/50', icon: 'i-lucide-x-circle' },
  'Later Line': { border: 'border-gray-200', bg: 'bg-gray-50/50', icon: 'i-lucide-clock-3' },
  'Watching': { border: 'border-blue-200', bg: 'bg-blue-50/50', icon: 'i-lucide-eye' },
  'Eligible Now': { border: 'border-teal-200', bg: 'bg-teal-50/50', icon: 'i-lucide-check-circle' },
  'Action Needed': { border: 'border-amber-200', bg: 'bg-amber-50/50', icon: 'i-lucide-alert-triangle' },
}

// Build columns from trials + cached stages
const funnelColumns = computed(() => {
  // Access stageVersion to trigger reactivity
  void stageVersion.value
  const columns: Record<FunnelStage, Array<{ trial: ResearchEntry; assessment: FunnelAssessment | null }>> = {
    'Excluded': [],
    'Later Line': [],
    'Watching': [],
    'Eligible Now': [],
    'Action Needed': [],
  }
  for (const trial of props.trials) {
    const assessment = getStage(trial.external_id)
    const stage: FunnelStage = assessment?.stage ?? 'Watching'
    columns[stage].push({ trial, assessment })
  }
  return columns
})

const unassessedCount = computed(() => {
  void stageVersion.value
  const all = getAllStages()
  return props.trials.filter(t => !all[t.external_id]).length
})

async function assessBatch(trials: ResearchEntry[]) {
  if (!trials.length) return
  assessError.value = null

  // Split into chunks of 15 (API max)
  const BATCH_SIZE = 15
  const chunks: ResearchEntry[][] = []
  for (let i = 0; i < trials.length; i += BATCH_SIZE) {
    chunks.push(trials.slice(i, i + BATCH_SIZE))
  }

  for (const chunk of chunks) {
    const ids = chunk.map(t => t.external_id)
    ids.forEach(id => assessingIds.value.add(id))

    try {
      const result = await $fetch<{
        assessments: Array<{
          nct_id: string
          oncofiles_id: number
          stage: FunnelStage
          exclusion_reason: string | null
          next_step: string
          deadline_note: string | null
        }>
        cost_usd: number
      }>(`/api/oncoteam/research/assess-funnel?patient_id=${useActivePatient().activePatientId.value || 'q1b'}`, {
        method: 'POST',
        body: {
          trials: chunk.map(t => ({
            id: t.id,
            external_id: t.external_id,
            title: t.title,
            summary: t.summary,
            relevance: t.relevance,
            relevance_reason: t.relevance_reason,
          })),
        },
      })

      for (const a of result.assessments) {
        setStage(a.nct_id, {
          stage: a.stage,
          exclusion_reason: a.exclusion_reason,
          next_step: a.next_step,
          deadline_note: a.deadline_note,
          assessed_at: new Date().toISOString(),
        })
      }
      stageVersion.value++
      scheduleSave()
    }
    catch (err) {
      assessError.value = err instanceof Error ? err.message : 'Assessment failed'
    }
    finally {
      ids.forEach(id => assessingIds.value.delete(id))
    }
  }
}

function handleMove(nctId: string, newStage: FunnelStage) {
  moveStage(nctId, newStage)
  stageVersion.value++
  scheduleSave()
}

function handleClick(trial: ResearchEntry) {
  drilldown.open({ type: 'research', id: trial.id, label: trial.title, data: { ...trial } })
}

function assessAll() {
  // Only re-assess trials that weren't manually moved — preserve user decisions
  const toAssess = props.trials.filter(t => {
    const existing = getStage(t.external_id)
    return !existing?.manually_moved
  })
  stageVersion.value++
  assessBatch(toAssess)
}

// Auto-assess unassessed trials when data is available
function autoAssessUnassessed() {
  if (!props.trials.length) return false
  const all = getAllStages()
  const unassessed = props.trials.filter(t => !all[t.external_id])
  if (unassessed.length > 0 && unassessed.length <= 15) {
    assessBatch(unassessed)
  }
  return true
}

// Debounced save to server after stage changes
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveToServer(), 2000)
}

onMounted(async () => {
  // Load persisted stages from server first
  await loadFromServer()
  stageVersion.value++

  if (!autoAssessUnassessed()) {
    // Data not yet loaded — watch for it to arrive
    const stop = watch(() => props.trials, () => {
      if (autoAssessUnassessed()) stop()
    })
  }
})
</script>

<template>
  <div class="space-y-3">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <UBadge v-if="unassessedCount > 0" variant="subtle" size="xs" color="warning">
          {{ unassessedCount }} unassessed
        </UBadge>
        <span v-if="assessingIds.size" class="text-xs text-gray-400 flex items-center gap-1">
          <UIcon name="i-lucide-loader-2" class="w-3 h-3 animate-spin" />
          Assessing {{ assessingIds.size }} trials...
        </span>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          icon="i-lucide-history"
          variant="ghost"
          size="xs"
          color="neutral"
          @click="showLog = !showLog"
        >
          Log
        </UButton>
        <UButton
          v-if="activeRole === 'advocate'"
          icon="i-lucide-sparkles"
          variant="soft"
          size="xs"
          color="primary"
          :loading="assessingIds.size > 0"
          @click="assessAll"
        >
          Assess All
        </UButton>
      </div>
    </div>

    <ApiErrorBanner :error="assessError" />

    <!-- Movement audit log -->
    <div v-if="showLog" class="rounded-xl border border-gray-200 bg-white p-4 max-h-64 overflow-y-auto">
      <h3 class="text-xs font-semibold text-gray-700 mb-2">Movement Audit Log</h3>
      <div v-if="getLog().length === 0" class="text-xs text-gray-400 py-3 text-center">No movements recorded yet</div>
      <div v-else class="space-y-1">
        <div v-for="(entry, i) in getLog().slice(0, 50)" :key="i" class="flex items-center gap-2 text-xs text-gray-600">
          <span class="text-gray-400 font-mono w-32 shrink-0">{{ new Date(entry.datetime).toLocaleString('sk-SK', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span>
          <code class="text-teal-700 text-[10px]">{{ entry.nct_id }}</code>
          <span class="text-gray-400">{{ entry.from }}</span>
          <UIcon name="i-lucide-arrow-right" class="w-3 h-3 text-gray-300" />
          <span class="font-medium">{{ entry.to }}</span>
          <UBadge variant="subtle" size="xs" :color="entry.actor === 'auto-assess' ? 'info' : 'warning'">
            {{ entry.actor }}
          </UBadge>
        </div>
      </div>
    </div>

    <!-- Kanban columns -->
    <div class="flex gap-3 overflow-x-auto pb-4">
      <div
        v-for="stage in FUNNEL_STAGES"
        :key="stage"
        class="w-72 flex-shrink-0 rounded-xl border p-3"
        :class="[COLUMN_STYLES[stage].border, COLUMN_STYLES[stage].bg]"
      >
        <!-- Column header -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-1.5">
            <UIcon :name="COLUMN_STYLES[stage].icon" class="w-4 h-4 text-gray-500" />
            <span class="text-xs font-semibold text-gray-700">{{ stage }}</span>
          </div>
          <UBadge variant="subtle" size="xs" color="neutral">
            {{ funnelColumns[stage].length }}
          </UBadge>
        </div>

        <!-- Cards -->
        <div class="space-y-2">
          <TrialFunnelCard
            v-for="item in funnelColumns[stage]"
            :key="item.trial.external_id"
            :trial="item.trial"
            :assessment="item.assessment"
            :is-assessing="assessingIds.has(item.trial.external_id)"
            :is-watched="isWatched(item.trial)"
            @move="(s) => handleMove(item.trial.external_id, s)"
            @click="handleClick(item.trial)"
            @toggle-active="() => { toggleActive(item.trial.external_id); stageVersion++ }"
          />
        </div>

        <!-- Empty state -->
        <div v-if="!funnelColumns[stage].length" class="text-xs text-gray-400 text-center py-6">
          No trials
        </div>
      </div>
    </div>
  </div>
</template>
