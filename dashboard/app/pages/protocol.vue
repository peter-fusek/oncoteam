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
  safety_flags: Record<string, { rule: string; source: string; label?: string; active?: boolean; severity?: string }>
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

// #377 — live funnel cards in the "Watching" stage. Rendered alongside the
// static protocol watchlist so the two sources stay distinguishable.
interface FunnelCard {
  card_id: string
  nct_id: string
  title: string
  current_stage: string
  source_agent?: string
}
const { data: funnelCards, refresh: refreshFunnelWatching } = fetchApi<{
  cards: FunnelCard[]
  count: number
}>('/funnel/cards?lane=clinical', { lazy: true, server: false })

const funnelWatching = computed(() =>
  (funnelCards.value?.cards ?? []).filter(c => c.current_stage === 'Watching')
)

const { t } = useI18n()
const { formatDate } = useFormatDate()

// Most recent lab sample date from protocol lab values
const lastLabDate = computed(() => {
  const labs = protocol.value?.last_lab_values
  if (!labs) return null
  let latest = ''
  for (const info of Object.values(labs)) {
    const d = info.sample_date || info.date || ''
    if (d > latest) latest = d
  }
  return latest || null
})

const activeTab = ref('checklist')
const expandedCycle = ref<number | null>(null)
const tabs = computed(() => [
  { key: 'checklist', label: t('protocol.tabs.checklist'), icon: 'i-lucide-clipboard-check' },
  { key: 'labs', label: t('protocol.tabs.labs'), icon: 'i-lucide-test-tube-diagonal' },
  { key: 'dosemods', label: t('protocol.tabs.dosemods'), icon: 'i-lucide-pill' },
  { key: 'cumdose', label: t('protocol.tabs.cumdose'), icon: 'i-lucide-activity' },
  { key: 'delays', label: t('protocol.tabs.delays'), icon: 'i-lucide-timer' },
  { key: 'safety', label: t('protocol.tabs.safety'), icon: 'i-lucide-shield-alert' },
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
        <h2 class="text-sm font-semibold text-gray-900 mb-2">{{ $t('protocol.doseTitle') }}</h2>
        <div class="flex items-center gap-2 mb-3 text-[10px] text-amber-600 bg-amber-50 rounded-md px-2.5 py-1.5 border border-amber-200">
          <UIcon name="i-lucide-calculator" class="w-3.5 h-3.5 shrink-0" />
          <span>{{ $t('protocol.doseCalculated') }}</span>
        </div>
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

      <!-- Safety Flags (#230) -->
      <div v-if="activeTab === 'safety'" class="space-y-2">
        <div
          v-for="(flag, key) in protocol.safety_flags"
          :key="key"
          class="rounded-lg border p-4 transition-all"
          :class="flag.active
            ? 'border-red-300 bg-red-50/50 ring-1 ring-red-200'
            : 'border-gray-200 bg-white opacity-60'"
        >
          <div class="flex items-center gap-2 mb-1">
            <UIcon
              :name="flag.active ? 'i-lucide-shield-alert' : 'i-lucide-shield-check'"
              :class="flag.active ? 'text-red-600' : 'text-green-600'"
              class="w-4 h-4 shrink-0"
            />
            <span class="text-sm font-medium" :class="flag.active ? 'text-red-900' : 'text-gray-600'">
              {{ flag.label || String(key).replace(/_/g, ' ') }}
            </span>
            <UBadge
              :color="flag.active ? 'error' : 'success'"
              variant="subtle"
              size="xs"
            >
              {{ flag.active ? (flag.severity === 'permanent' ? $t('protocol.flagPermanent') : $t('protocol.flagActive')) : $t('protocol.flagInactive') }}
            </UBadge>
          </div>
          <div class="text-xs text-gray-500 ml-6">{{ flag.rule }}</div>
          <div class="text-[10px] text-gray-400 ml-6 mt-0.5">{{ flag.source }}</div>
        </div>
      </div>

      <!-- Milestones -->
      <div v-if="activeTab === 'milestones'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.milestonesTitle') }}</h2>
        <MilestoneTracker :milestones="protocol.milestones" :current-cycle="protocol.current_cycle" :cycle-history="cycleHistory?.cycles" />
      </div>

      <!-- Monitoring Schedule -->
      <div v-if="activeTab === 'monitoring'" class="rounded-xl border border-gray-200 bg-white p-5">
        <h2 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('protocol.monitoringTitle') }}</h2>
        <!-- Last labs summary -->
        <div v-if="lastLabDate" class="flex items-center gap-2 mb-4 text-xs text-gray-500">
          <UIcon name="i-lucide-test-tube-diagonal" class="w-3.5 h-3.5" />
          <span>{{ $t('protocol.lastLabCheck') }}: <strong class="text-gray-700">{{ formatDate(lastLabDate) }}</strong></span>
        </div>
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

      <!-- Watched Trials: two sources — static protocol list + live clinical funnel (#377) -->
      <div v-if="activeTab === 'trials'" class="space-y-4">
        <!-- A. Curated protocol watchlist (static, advocate-maintained) -->
        <div>
          <div class="flex items-baseline gap-2 mb-1.5">
            <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              {{ $t('protocol.trialsProtocolHeader', 'Curated by protocol') }}
            </h3>
            <span class="text-[10px] text-gray-400">
              {{ $t('protocol.trialsProtocolHint', 'Edited by advocate — stable reference list') }}
            </span>
          </div>
          <div class="space-y-1.5">
            <div
              v-for="trial in protocol.watched_trials"
              :key="trial"
              class="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-2.5 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
              @click="drilldown.open({ type: 'protocol_section', id: `trial-${trial}`, label: trial, data: { trial, status: 'Watched', source: 'Protocol watchlist' } })"
            >
              <UIcon name="i-lucide-eye" class="text-teal-500 shrink-0" />
              <span class="text-sm text-gray-700 flex-1">{{ trial }}</span>
              <UBadge variant="subtle" size="xs" color="neutral">{{ $t('protocol.static', 'static') }}</UBadge>
            </div>
          </div>
        </div>

        <!-- B. Live clinical funnel — cards physician has promoted to "Watching" -->
        <div>
          <div class="flex items-baseline gap-2 mb-1.5">
            <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              {{ $t('protocol.trialsFunnelHeader', 'Clinical funnel — Watching') }}
            </h3>
            <span class="text-[10px] text-gray-400">
              {{ $t('protocol.trialsFunnelHint', 'Physician-promoted trials from the proposals lane') }}
            </span>
            <UButton
              icon="i-lucide-refresh-cw"
              variant="ghost"
              size="xs"
              color="neutral"
              class="ml-auto"
              @click="refreshFunnelWatching"
            />
          </div>
          <div v-if="funnelWatching.length" class="space-y-1.5">
            <div
              v-for="card in funnelWatching"
              :key="card.card_id"
              class="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50/40 px-4 py-2.5"
            >
              <UIcon name="i-lucide-kanban" class="text-indigo-600 shrink-0" />
              <a
                :href="`https://clinicaltrials.gov/study/${card.nct_id}`"
                target="_blank"
                rel="noopener"
                class="font-mono text-xs text-indigo-800 hover:underline"
              >
                {{ card.nct_id }}
              </a>
              <span class="text-sm text-gray-700 flex-1 truncate">{{ card.title }}</span>
              <UBadge v-if="card.source_agent" variant="subtle" size="xs" color="neutral">
                {{ card.source_agent }}
              </UBadge>
            </div>
          </div>
          <div v-else class="text-xs text-gray-400 italic px-1">
            {{ $t('protocol.trialsFunnelEmpty', 'No trials promoted to Watching yet. Agents propose in /research → Proposals; physician promotes with rationale.') }}
          </div>
        </div>

        <!-- Navigation to full research + funnel -->
        <div class="flex items-center gap-3 pt-2 border-t border-gray-100">
          <NuxtLink to="/research" class="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700 hover:text-teal-900 transition-colors">
            <UIcon name="i-lucide-flask-conical" class="w-4 h-4" />
            {{ $t('protocol.allResearch') }}
          </NuxtLink>
          <span class="text-gray-300">|</span>
          <NuxtLink to="/research?tab=funnel" class="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700 hover:text-teal-900 transition-colors">
            <UIcon name="i-lucide-kanban" class="w-4 h-4" />
            {{ $t('protocol.researchFunnel') }}
          </NuxtLink>
        </div>
      </div>
    </div>

    <!-- #382 — every threshold + dose-mod rule links to its clinical source. -->
    <ClinicalSourceFooter
      :sources="[
        { label: 'ESMO 2022 mCRC Living Guidelines', url: 'https://www.esmo.org/guidelines/guidelines-by-topic/gastrointestinal-cancers/metastatic-colorectal-cancer' },
        { label: 'NCCN Colon v3.2024 §TOX-1', url: 'https://www.nccn.org/guidelines/category_1' },
        { label: 'ASH 2021 VTE in Cancer (platelet rules on LMWH)', url: 'https://ashpublications.org/bloodadvances/article/5/4/927/475154' },
      ]"
    />
  </div>
</template>
