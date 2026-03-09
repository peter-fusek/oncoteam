<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: protocol, refresh } = await fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; note?: string; action: string }>
  dose_modifications: Record<string, string>
  milestones: Array<{ cycle: number; action: string; description: string }>
  monitoring_schedule: Record<string, string>
  safety_flags: Record<string, { rule: string; source: string }>
  second_line_options: Array<{ regimen: string; evidence: string; note: string }>
  watched_trials: string[]
  cycle_delay_rules: Array<{ condition: string; action: string }>
  current_cycle: number
}>('/protocol')

const { data: cumDose } = await fetchApi<{
  drug: string
  cumulative_mg_m2: number
  cycles_counted: number
  dose_per_cycle: number
  thresholds_reached: Array<{ at: number; action: string; severity: string }>
  next_threshold: { at: number; action: string; severity: string } | null
  pct_to_next: number
  all_thresholds: Array<{ at: number; action: string; severity: string }>
  max_recommended: number
}>('/cumulative-dose')

const { t } = useI18n()

const activeTab = ref('checklist')
const tabs = computed(() => [
  { key: 'checklist', label: t('protocol.tabs.checklist'), icon: 'i-lucide-clipboard-check' },
  { key: 'labs', label: t('protocol.tabs.labs'), icon: 'i-lucide-test-tube-diagonal' },
  { key: 'dosemods', label: t('protocol.tabs.dosemods'), icon: 'i-lucide-pill' },
  { key: 'cumdose', label: t('protocol.tabs.cumdose'), icon: 'i-lucide-activity' },
  { key: 'delays', label: t('protocol.tabs.delays'), icon: 'i-lucide-timer' },
  { key: 'milestones', label: t('protocol.tabs.milestones'), icon: 'i-lucide-milestone' },
  { key: 'monitoring', label: t('protocol.tabs.monitoring'), icon: 'i-lucide-calendar' },
  { key: '2l', label: t('protocol.tabs.secondLine'), icon: 'i-lucide-arrow-right-circle' },
  { key: 'trials', label: t('protocol.tabs.trials'), icon: 'i-lucide-eye' },
])
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('protocol.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('protocol.subtitle') }}</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <!-- Tab navigation -->
    <div class="flex gap-2 flex-wrap">
      <UButton
        v-for="tab in tabs"
        :key="tab.key"
        :icon="tab.icon"
        :variant="activeTab === tab.key ? 'solid' : 'ghost'"
        :color="activeTab === tab.key ? 'primary' : 'neutral'"
        size="xs"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </UButton>
    </div>

    <div v-if="protocol">
      <!-- Pre-Cycle Checklist -->
      <div v-if="activeTab === 'checklist'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <PreCycleChecklist :current-cycle="protocol.current_cycle" />
      </div>

      <!-- Lab Thresholds -->
      <div v-if="activeTab === 'labs'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">{{ $t('protocol.labThresholds') }}</h2>
        <LabThresholdTable :thresholds="protocol.lab_thresholds" />
      </div>

      <!-- Dose Modifications -->
      <div v-if="activeTab === 'dosemods'" class="space-y-2">
        <DoseModCard
          v-for="(action, toxicity) in protocol.dose_modifications"
          :key="toxicity"
          :toxicity="toxicity"
          :action="action"
        />
      </div>

      <!-- Cumulative Dose -->
      <div v-if="activeTab === 'cumdose' && cumDose" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">{{ $t('protocol.doseTitle') }}</h2>
        <div class="mb-4">
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm text-gray-300">
              {{ cumDose.cumulative_mg_m2 }} {{ cumDose.unit }}
              <span class="text-gray-500">({{ cumDose.cycles_counted }} cycles × {{ cumDose.dose_per_cycle }})</span>
            </span>
            <span class="text-sm text-gray-400">{{ $t('protocol.doseMax') }}: {{ cumDose.max_recommended }} {{ cumDose.unit }}</span>
          </div>
          <!-- Progress bar -->
          <div class="relative h-4 rounded-full bg-gray-800 overflow-hidden">
            <div
              class="h-full rounded-full transition-all"
              :class="cumDose.pct_to_next >= 100 ? 'bg-red-500' : cumDose.thresholds_reached.length >= 2 ? 'bg-amber-500' : 'bg-teal-500'"
              :style="{ width: `${Math.min((cumDose.cumulative_mg_m2 / cumDose.max_recommended) * 100, 100)}%` }"
            />
            <!-- Threshold markers -->
            <div
              v-for="t in cumDose.all_thresholds"
              :key="t.at"
              class="absolute top-0 bottom-0 w-px"
              :class="t.severity === 'critical' ? 'bg-red-500/60' : 'bg-amber-500/60'"
              :style="{ left: `${(t.at / cumDose.max_recommended) * 100}%` }"
            />
          </div>
        </div>
        <!-- Threshold list -->
        <div class="space-y-2">
          <div
            v-for="t in cumDose.all_thresholds"
            :key="t.at"
            class="flex items-center gap-3 text-sm py-1"
            :class="cumDose.cumulative_mg_m2 >= t.at ? 'text-white' : 'text-gray-500'"
          >
            <UIcon
              :name="cumDose.cumulative_mg_m2 >= t.at ? 'i-lucide-check-circle' : 'i-lucide-circle'"
              :class="t.severity === 'critical' ? 'text-red-500' : 'text-amber-500'"
            />
            <span class="font-mono text-xs w-20">{{ t.at }} {{ cumDose.unit }}</span>
            <span>{{ t.action }}</span>
          </div>
        </div>
        <div v-if="cumDose.next_threshold" class="mt-3 text-xs text-gray-400">
          {{ $t('protocol.doseNextThreshold', { at: cumDose.next_threshold.at, unit: cumDose.unit, pct: cumDose.pct_to_next }) }}
        </div>
      </div>

      <!-- Cycle Delay Rules -->
      <div v-if="activeTab === 'delays'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">{{ $t('protocol.delayRules') }}</h2>
        <div class="space-y-1">
          <div
            v-for="(rule, i) in protocol.cycle_delay_rules"
            :key="i"
            class="flex items-start gap-3 py-2 border-b border-gray-800/50 last:border-0"
          >
            <UIcon
              name="i-lucide-clock"
              :class="rule.action.toLowerCase().includes('hold') || rule.action.toLowerCase().includes('mandatory') ? 'text-red-500' : 'text-amber-500'"
              class="mt-0.5 shrink-0"
            />
            <div>
              <div class="text-sm text-white">{{ rule.condition }}</div>
              <div class="text-xs text-gray-400">{{ rule.action }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Milestones -->
      <div v-if="activeTab === 'milestones'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">{{ $t('protocol.milestonesTitle') }}</h2>
        <MilestoneTracker :milestones="protocol.milestones" :current-cycle="protocol.current_cycle" />
      </div>

      <!-- Monitoring Schedule -->
      <div v-if="activeTab === 'monitoring'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">{{ $t('protocol.monitoringTitle') }}</h2>
        <div class="space-y-2">
          <div
            v-for="(schedule, item) in protocol.monitoring_schedule"
            :key="item"
            class="flex items-start gap-3 py-2 border-b border-gray-800/50 last:border-0"
          >
            <UIcon name="i-lucide-clock" class="text-gray-600 mt-0.5 shrink-0" />
            <div>
              <div class="text-sm text-white">{{ item.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()) }}</div>
              <div class="text-xs text-gray-500">{{ schedule }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Second-Line Options -->
      <div v-if="activeTab === '2l'" class="space-y-2">
        <div
          v-for="(opt, i) in protocol.second_line_options"
          :key="i"
          class="rounded-lg border border-gray-800 bg-gray-900/50 p-4"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-white">{{ i + 1 }}.</span>
            <span class="text-sm font-medium text-white">{{ opt.regimen }}</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">{{ opt.evidence }}</div>
          <div class="text-xs text-gray-500 mt-0.5 italic">{{ opt.note }}</div>
        </div>
      </div>

      <!-- Watched Trials -->
      <div v-if="activeTab === 'trials'" class="space-y-2">
        <div
          v-for="trial in protocol.watched_trials"
          :key="trial"
          class="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3"
        >
          <UIcon name="i-lucide-eye" class="text-teal-500 shrink-0" />
          <span class="text-sm text-gray-300">{{ trial }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
