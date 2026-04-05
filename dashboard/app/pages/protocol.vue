<script setup lang="ts">
const { isGeneralHealth } = usePatientType()

// Redirect general health patients — protocol page is oncology-only
watchEffect(() => {
  if (isGeneralHealth.value) navigateTo('/')
})

const { fetchApi } = useOncoteamApi()
const drilldown = useDrilldown()

const { data: protocol, status: protocolStatus, error: protocolError, refresh } = fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; note?: string; action: string }>
  dose_modifications: Record<string, string>
  milestones: Array<{ cycle: number; action: string; description: string }>
  monitoring_schedule: Record<string, string>
  safety_flags: Record<string, { rule: string; source: string }>
  second_line_options: Array<{ regimen: string; evidence: string; note: string }>
  watched_trials: string[]
  cycle_delay_rules: Array<{ condition: string; action: string }>
  current_cycle: number
  last_lab_values?: Record<string, { value: number; sample_date?: string; sync_date?: string; date?: string; status: 'safe' | 'warning' | 'critical' }>
  real_values?: {
    dose_modifications?: { last_change: string; date: string }
    current_regimen?: { regimen: string; cycle: number }
    nutrition?: { weight_kg: number; date: string; baseline_kg: number }
  }
}>('/protocol', { lazy: true, server: false, timeout: 15000 })

const { data: cumDose } = fetchApi<{
  drug: string
  cumulative_mg_m2: number
  cycles_counted: number
  dose_per_cycle: number
  thresholds_reached: Array<{ at: number; action: string; severity: string }>
  next_threshold: { at: number; action: string; severity: string } | null
  pct_to_next: number
  all_thresholds: Array<{ at: number; action: string; severity: string }>
  max_recommended: number
}>('/cumulative-dose', { lazy: true, server: false })

const { data: cycleHistory } = fetchApi<{
  cycles: Array<{
    cycle_number: number
    date: string
    lab_evaluation: Record<string, { value: number; threshold: number | null; unit: string; pass: boolean }>
    overall_pass: boolean
    source_event_id: number | null
  }>
  current_cycle: number
}>('/protocol/cycles', { lazy: true, server: false })

const { t } = useI18n()

const activeTab = ref('checklist')
const expandedCycle = ref<number | null>(null)
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
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('protocol.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('protocol.subtitle') }}</p>
        <LastUpdated :timestamp="protocol?.last_updated" />
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <!-- Tab navigation -->
    <div class="flex gap-2 flex-wrap">
      <UButton
        v-for="tab in tabs"
        :key="tab.key"
        :icon="tab.icon"
        :variant="activeTab === tab.key ? 'solid' : 'soft'"
        :color="activeTab === tab.key ? 'primary' : 'neutral'"
        size="xs"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </UButton>
    </div>

    <SkeletonLoader v-if="!protocol && protocolStatus === 'pending'" variant="card" />
    <ApiErrorBanner v-else-if="!protocol && protocolStatus === 'error'" :error="protocolError?.message || 'Failed to load protocol'" />
    <div v-else-if="protocol">
      <!-- Pre-Cycle Checklist -->
      <div v-if="activeTab === 'checklist'">
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <PreCycleChecklist
            :current-cycle="protocol.current_cycle"
            :last-lab-values="protocol.last_lab_values"
            :lab-thresholds="protocol.lab_thresholds"
          />
        </div>

        <!-- Previous cycles -->
        <div v-if="cycleHistory?.cycles?.length" class="mt-6">
          <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            {{ $t('protocol.previousCycles') }}
          </h3>
          <div v-for="cycle in cycleHistory.cycles" :key="cycle.cycle_number"
               class="rounded-lg border border-gray-200 bg-white mb-2">
            <button class="w-full px-4 py-3 flex items-center justify-between text-left"
                    @click="expandedCycle = expandedCycle === cycle.cycle_number ? null : cycle.cycle_number">
              <span class="text-sm text-gray-900">{{ $t('components.milestone.cycle', { n: cycle.cycle_number }) }}</span>
              <div class="flex items-center gap-2">
                <span v-if="cycle.date" class="text-xs text-gray-500">{{ cycle.date }}</span>
                <UBadge :color="cycle.overall_pass ? 'success' : 'error'" variant="subtle" size="xs">
                  {{ cycle.overall_pass ? $t('protocol.passed') : $t('protocol.issues') }}
                </UBadge>
                <UIcon
                  :name="expandedCycle === cycle.cycle_number ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                  class="w-4 h-4 text-gray-500"
                />
              </div>
            </button>
            <div v-if="expandedCycle === cycle.cycle_number" class="px-4 pb-4">
              <PreCycleChecklist :current-cycle="cycle.cycle_number" :lab-values="cycle.lab_evaluation" readonly />
            </div>
          </div>
        </div>
      </div>

      <!-- Lab Thresholds -->
      <div v-if="activeTab === 'labs'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.labThresholds') }}</h2>
        <LabThresholdTable
          :thresholds="protocol.lab_thresholds"
          :last-values="protocol.last_lab_values"
          @row-click="(param: string) => drilldown.open({ type: 'treatment_event', id: `lab-${param}`, label: `${param} threshold`, data: { parameter: param, ...protocol.lab_thresholds[param], last_value: protocol.last_lab_values?.[param] } })"
        />
      </div>

      <!-- Dose Modifications -->
      <div v-if="activeTab === 'dosemods'" class="space-y-2">
        <!-- Current regimen info -->
        <div v-if="protocol.real_values?.current_regimen" class="rounded-lg border border-gray-200 bg-white px-4 py-3 flex items-center gap-4 text-sm mb-2">
          <span class="text-gray-500">{{ $t('protocol.currentRegimen') }}:</span>
          <span class="text-gray-900 font-medium">{{ protocol.real_values.current_regimen.regimen }}</span>
          <span class="text-gray-500">{{ $t('components.milestone.cycle', { n: protocol.real_values.current_regimen.cycle }) }}</span>
          <template v-if="protocol.real_values.dose_modifications">
            <span class="text-gray-700">|</span>
            <span class="text-amber-600 text-xs">{{ protocol.real_values.dose_modifications.last_change }} ({{ protocol.real_values.dose_modifications.date }})</span>
          </template>
        </div>
        <div
          v-for="(action, toxicity) in protocol.dose_modifications"
          :key="toxicity"
          class="cursor-pointer hover:ring-1 hover:ring-teal-500/30 rounded-xl transition-all"
          @click="drilldown.open({ type: 'protocol_section', id: `dosemod-${toxicity}`, label: String(toxicity).replace(/_/g, ' '), data: { toxicity, action, source: 'ESMO/NCCN mFOLFOX6 guidelines' } })"
        >
          <DoseModCard :toxicity="toxicity" :action="action" />
        </div>
      </div>

      <!-- Cumulative Dose -->
      <div v-if="activeTab === 'cumdose' && cumDose" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.doseTitle') }}</h2>
        <div class="mb-4">
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm text-gray-700">
              {{ cumDose.cumulative_mg_m2 }} {{ cumDose.unit }}
              <span class="text-gray-500">({{ cumDose.cycles_counted }} cycles × {{ cumDose.dose_per_cycle }})</span>
            </span>
            <span class="text-sm text-gray-400">{{ $t('protocol.doseMax') }}: {{ cumDose.max_recommended }} {{ cumDose.unit }}</span>
          </div>
          <!-- Progress bar -->
          <div class="relative h-4 rounded-full bg-gray-100 overflow-hidden">
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
            :class="cumDose.cumulative_mg_m2 >= t.at ? 'text-gray-900' : 'text-gray-500'"
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
      <div v-if="activeTab === 'delays'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.delayRules') }}</h2>
        <div class="space-y-1">
          <div
            v-for="(rule, i) in protocol.cycle_delay_rules"
            :key="i"
            class="flex items-start gap-3 py-2 border-b border-gray-100 last:border-0 cursor-pointer hover:bg-gray-50 rounded-lg px-2 -mx-2 transition-colors"
            @click="drilldown.open({ type: 'protocol_section', id: `delay-${i}`, label: rule.condition, data: { condition: rule.condition, action: rule.action, source: 'ESMO/NCCN cycle delay guidelines' } })"
          >
            <UIcon
              name="i-lucide-clock"
              :class="rule.action.toLowerCase().includes('hold') || rule.action.toLowerCase().includes('mandatory') ? 'text-red-500' : 'text-amber-500'"
              class="mt-0.5 shrink-0"
            />
            <div class="flex-1">
              <div class="text-sm text-gray-900">{{ rule.condition }}</div>
              <div class="text-xs text-gray-400">{{ rule.action }}</div>
            </div>
            <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 mt-1 shrink-0" />
          </div>
        </div>
      </div>

      <!-- Milestones -->
      <div v-if="activeTab === 'milestones'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.milestonesTitle') }}</h2>
        <MilestoneTracker :milestones="protocol.milestones" :current-cycle="protocol.current_cycle" />
      </div>

      <!-- Monitoring Schedule -->
      <div v-if="activeTab === 'monitoring'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.monitoringTitle') }}</h2>
        <div class="space-y-2">
          <div
            v-for="(schedule, item) in protocol.monitoring_schedule"
            :key="item"
            class="flex items-start gap-3 py-2 border-b border-gray-100 last:border-0 cursor-pointer hover:bg-gray-50 rounded-lg px-2 -mx-2 transition-colors"
            @click="drilldown.open({ type: 'protocol_section', id: `monitor-${item}`, label: String(item).replace(/_/g, ' '), data: { item: String(item).replace(/_/g, ' '), schedule, source: 'mFOLFOX6 monitoring protocol' } })"
          >
            <UIcon name="i-lucide-clock" class="text-gray-600 mt-0.5 shrink-0" />
            <div class="flex-1">
              <div class="text-sm text-gray-900">{{ item.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()) }}</div>
              <div class="text-xs text-gray-500">{{ schedule }}</div>
            </div>
            <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 mt-1 shrink-0" />
          </div>
        </div>
      </div>

      <!-- Second-Line Options -->
      <div v-if="activeTab === '2l'" class="space-y-2">
        <div
          v-for="(opt, i) in protocol.second_line_options"
          :key="i"
          class="rounded-lg border border-gray-200 bg-white p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
          @click="drilldown.open({ type: 'protocol_section', id: `2l-${i}`, label: opt.regimen, data: { regimen: opt.regimen, evidence: opt.evidence, note: opt.note, ranking: i + 1, source: 'ESMO/NCCN 2L options for KRAS-mutant mCRC' } })"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-900">{{ i + 1 }}.</span>
            <span class="text-sm font-medium text-gray-900">{{ opt.regimen }}</span>
            <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 ml-auto" />
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
          class="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
          @click="drilldown.open({ type: 'protocol_section', id: `trial-${trial}`, label: trial, data: { trial, status: 'Watched', relevance: 'KRAS G12S mCRC', source: 'ClinicalTrials.gov' } })"
        >
          <UIcon name="i-lucide-eye" class="text-teal-500 shrink-0" />
          <span class="text-sm text-gray-700 flex-1">{{ trial }}</span>
          <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0" />
        </div>
      </div>
    </div>
  </div>
</template>
