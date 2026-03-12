<script setup lang="ts">
import type { RoomDef } from '~/composables/useRoomNavigation'

const { fetchApi } = useOncoteamApi()
const { t } = useI18n()

const {
  currentLevel, selectedRoom, selectedWorker, lastViewed,
  markViewed, openRoom, openWorker, goBack, goToGrid,
} = useRoomNavigation()

// ── Data fetching ────────────────────────────────

const { data: status, status: statusFetch, refresh: refreshStatus } = fetchApi<{
  status: string; version: string; session_id: string; tools_count: number
}>('/status', { lazy: true })

const { data: stats, refresh: refreshStats } = fetchApi<{
  stats: Array<{ tool_name: string; status: string; count: number; avg_duration_ms: number }>
}>('/stats', { lazy: true })

const { data: activity, refresh: refreshActivity } = fetchApi<{
  entries: Array<{
    tool: string; status: string; duration_ms: number; timestamp: string
    input: string; output: string; error: string
  }>
  total: number
}>('/activity?limit=100', { lazy: true })

const { data: autonomous, refresh: refreshAutonomous } = fetchApi<{
  enabled: boolean; daily_cost: number
  jobs?: Array<{ id: string; schedule: string; description: string; assigned_tool?: string }>
}>('/autonomous', { lazy: true })

const { data: costData, refresh: refreshCost } = fetchApi<{
  today_spend: number; daily_cap: number; mtd_spend: number
  expected_eom: number; remaining_credit: number; total_credit: number
  days_remaining: number; budget_alert: boolean; month: string
}>('/autonomous/cost', { lazy: true })

const { data: gamification, refresh: refreshGamification } = useFetch<{
  totalXp: number; level: string; streakDays: number
}>('/api/gamification', { lazy: true })

const { data: labData, refresh: refreshLabs } = fetchApi<{
  entries: Array<{
    date: string
    alerts: Array<{ param: string; value: number; threshold: number; action: string }>
  }>
}>('/labs?limit=3', { lazy: true })

// ── Helpers ──────────────────────────────────────

function toolLabel(toolName: string): string {
  const key = `agents.toolNames.${toolName}`
  const label = t(key)
  return label === key ? toolName.replace(/_/g, ' ') : label
}

const toolStatsMap = computed(() =>
  new Map((stats.value?.stats ?? []).map(s => [s.tool_name, s]))
)

const autonomousJobsMap = computed(() =>
  new Map((autonomous.value?.jobs ?? []).map(j => [j.id, j]))
)

const toolJobsMap = computed(() => {
  const map = new Map<string, Array<{ id: string; schedule: string; description: string }>>()
  for (const job of (autonomous.value?.jobs ?? [])) {
    const tool = job.assigned_tool
    if (tool) {
      if (!map.has(tool)) map.set(tool, [])
      map.get(tool)!.push(job)
    }
  }
  return map
})

function getAgentStatus(tools: string[]): 'active' | 'recent' | 'idle' {
  const recent = activity.value?.entries ?? []
  const lastAct = recent.find(e => tools.includes(e.tool))
  if (!lastAct) return 'idle'
  const age = Date.now() - new Date(lastAct.timestamp).getTime()
  if (age < 5 * 60_000) return 'active'
  if (age < 60 * 60_000) return 'recent'
  return 'idle'
}

function statusLabel(s: string) {
  if (s === 'active') return t('agents.statusActive')
  if (s === 'recent') return t('agents.statusRecent')
  return t('agents.statusIdle')
}

function newCountForTools(tools: string[]): number {
  const cutoff = new Date(lastViewed.value).getTime()
  return (activity.value?.entries ?? []).filter(
    e => tools.includes(e.tool) && new Date(e.timestamp).getTime() > cutoff
  ).length
}

function entriesForTools(tools: string[]) {
  return (activity.value?.entries ?? []).filter(e => tools.includes(e.tool))
}

function lastActivityFor(tool: string) {
  return (activity.value?.entries ?? []).find(e => e.tool === tool) ?? null
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return t('agents.statusActive').toLowerCase()
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
}

// ── Room definitions ─────────────────────────────

const rooms = computed<RoomDef[]>(() => [
  {
    key: 'researchLab',
    name: t('agents.rooms.researchLab'),
    desc: t('agents.rooms.researchLabDesc'),
    icon: 'i-lucide-flask-conical',
    color: 'from-blue-500/20 to-blue-600/10',
    border: 'border-blue-500/30',
    statusColor: 'bg-blue-500',
    tools: ['search_pubmed', 'search_clinical_trials', 'search_clinical_trials_adjacent'],
    autonomousJobs: ['daily_research', 'trial_monitor'],
    status: getAgentStatus(['search_pubmed', 'search_clinical_trials', 'search_clinical_trials_adjacent']),
    totalCalls: ['search_pubmed', 'search_clinical_trials', 'search_clinical_trials_adjacent']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'eligibilityCheck',
    name: t('agents.rooms.eligibilityCheck'),
    desc: t('agents.rooms.eligibilityCheckDesc'),
    icon: 'i-lucide-target',
    color: 'from-amber-500/20 to-amber-600/10',
    border: 'border-amber-500/30',
    statusColor: 'bg-amber-500',
    tools: ['check_trial_eligibility', 'fetch_trial_details', 'fetch_pubmed_article'],
    autonomousJobs: [],
    status: getAgentStatus(['check_trial_eligibility', 'fetch_trial_details', 'fetch_pubmed_article']),
    totalCalls: ['check_trial_eligibility', 'fetch_trial_details', 'fetch_pubmed_article']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'clinicalProtocol',
    name: t('agents.rooms.clinicalProtocol'),
    desc: t('agents.rooms.clinicalProtocolDesc'),
    icon: 'i-lucide-shield-check',
    color: 'from-red-500/20 to-red-600/10',
    border: 'border-red-500/30',
    statusColor: 'bg-red-500',
    tools: ['pre_cycle_check', 'tumor_marker_review', 'response_assessment'],
    autonomousJobs: ['pre_cycle_check', 'tumor_marker_review', 'response_assessment'],
    status: getAgentStatus(['pre_cycle_check', 'tumor_marker_review', 'response_assessment']),
    totalCalls: ['pre_cycle_check', 'tumor_marker_review', 'response_assessment']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'analyticsRoom',
    name: t('agents.rooms.analyticsRoom'),
    desc: t('agents.rooms.analyticsRoomDesc'),
    icon: 'i-lucide-bar-chart-3',
    color: 'from-purple-500/20 to-purple-600/10',
    border: 'border-purple-500/30',
    statusColor: 'bg-purple-500',
    tools: ['analyze_labs', 'compare_labs', 'get_lab_trends'],
    autonomousJobs: [],
    status: getAgentStatus(['analyze_labs', 'compare_labs', 'get_lab_trends']),
    totalCalls: ['analyze_labs', 'compare_labs', 'get_lab_trends']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'reportRoom',
    name: t('agents.rooms.reportRoom'),
    desc: t('agents.rooms.reportRoomDesc'),
    icon: 'i-lucide-file-text',
    color: 'from-green-500/20 to-green-600/10',
    border: 'border-green-500/30',
    statusColor: 'bg-green-500',
    tools: ['daily_briefing', 'summarize_session', 'review_session'],
    autonomousJobs: ['weekly_briefing', 'mtb_preparation'],
    status: getAgentStatus(['daily_briefing', 'summarize_session', 'review_session']),
    totalCalls: ['daily_briefing', 'summarize_session', 'review_session']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'documentVault',
    name: t('agents.rooms.documentVault'),
    desc: t('agents.rooms.documentVaultDesc'),
    icon: 'i-lucide-archive',
    color: 'from-cyan-500/20 to-cyan-600/10',
    border: 'border-cyan-500/30',
    statusColor: 'bg-cyan-500',
    tools: ['search_documents', 'view_document', 'get_patient_context'],
    autonomousJobs: ['file_scan'],
    status: getAgentStatus(['search_documents', 'view_document', 'get_patient_context']),
    totalCalls: ['search_documents', 'view_document', 'get_patient_context']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
  {
    key: 'sessionLog',
    name: t('agents.rooms.sessionLog'),
    desc: t('agents.rooms.sessionLogDesc'),
    icon: 'i-lucide-notebook-pen',
    color: 'from-rose-500/20 to-rose-600/10',
    border: 'border-rose-500/30',
    statusColor: 'bg-rose-500',
    tools: ['log_research_decision', 'log_session_note', 'create_improvement_issue'],
    autonomousJobs: [],
    status: getAgentStatus(['log_research_decision', 'log_session_note', 'create_improvement_issue']),
    totalCalls: ['log_research_decision', 'log_session_note', 'create_improvement_issue']
      .reduce((sum, t) => sum + (toolStatsMap.value.get(t)?.count ?? 0), 0),
  },
])

// ── Key Insights ─────────────────────────────────

function formatInsight(entry: { tool: string; input: string; output: string }): { line1: string; line2: string } {
  // Line 1: What was searched/analyzed (from input)
  const qm = entry.input?.match(/query='([^']*)'/) || entry.input?.match(/condition='([^']*)'/)
  const q = qm?.[1]
  const line1 = q
    ? (q.length > 60 ? q.slice(0, 60) + '…' : q)
    : (entry.input?.length > 60 ? entry.input.slice(0, 60) + '…' : entry.input || entry.tool)

  // Line 2: Key finding (from output — extract count + first item)
  const countMatch = entry.output?.match(/(\d+)\s+(articles?|trials?|results?|documents?|entries)/i)
  const line2 = countMatch
    ? `${countMatch[1]} ${countMatch[2]}`
    : (entry.output?.length > 80 ? entry.output.slice(0, 80) + '…' : entry.output || '')

  return { line1, line2 }
}

function keyInsightsForTools(tools: string[], limit = 5) {
  return (activity.value?.entries ?? [])
    .filter(e => tools.includes(e.tool) && e.status === 'ok' && e.output)
    .slice(0, limit)
    .map(e => ({ tool: e.tool, timestamp: e.timestamp, insight: formatInsight(e), entry: e }))
}

const roomInsights = computed(() =>
  selectedRoom.value ? keyInsightsForTools(selectedRoom.value.tools) : []
)

const workerInsights = computed(() =>
  selectedWorker.value ? keyInsightsForTools([selectedWorker.value]) : []
)

// ── Drilldown integration ────────────────────────

const drilldown = useDrilldown()

function openTaskDetail(entry: { tool: string; status: string; duration_ms: number; timestamp: string; input: string; output: string; error: string }) {
  drilldown.open({
    type: 'activity',
    id: entry.timestamp,
    label: toolLabel(entry.tool),
    data: {
      tool: entry.tool,
      status: entry.status,
      duration_ms: entry.duration_ms,
      timestamp: entry.timestamp,
      input: entry.input,
      output: entry.output,
      error: entry.error,
    },
  })
}

// ── Computed for current view ────────────────────

const recentAlerts = computed(() => {
  if (!labData.value?.entries) return []
  return labData.value.entries
    .filter(e => e.alerts?.length)
    .flatMap(e => e.alerts.map(a => ({ ...a, date: e.date })))
})

const daysSinceLastLabs = computed(() => {
  if (!labData.value?.entries?.length) return null
  const latest = labData.value.entries[0]?.date
  if (!latest) return null
  const diff = Date.now() - new Date(latest).getTime()
  return Math.floor(diff / 86400000)
})

const roomEntries = computed(() =>
  selectedRoom.value ? entriesForTools(selectedRoom.value.tools) : []
)

const workerEntries = computed(() =>
  selectedWorker.value
    ? (activity.value?.entries ?? []).filter(e => e.tool === selectedWorker.value)
    : []
)

const workerJobs = computed(() =>
  selectedWorker.value ? (toolJobsMap.value.get(selectedWorker.value) ?? []) : []
)

const roomJobs = computed(() => {
  if (!selectedRoom.value) return []
  return selectedRoom.value.autonomousJobs
    .map(id => autonomousJobsMap.value.get(id))
    .filter(Boolean) as Array<{ id: string; schedule: string; description: string }>
})

// ── Refresh ──────────────────────────────────────

async function refreshAll() {
  await Promise.all([refreshStatus(), refreshStats(), refreshActivity(), refreshAutonomous(), refreshCost(), refreshGamification(), refreshLabs()])
}

const refreshInterval = ref<ReturnType<typeof setInterval>>()
onMounted(() => {
  // Mark viewed AFTER computing badge counts from the stale timestamp
  nextTick(() => markViewed())
  refreshInterval.value = setInterval(refreshAll, 30_000)
})
onUnmounted(() => {
  clearInterval(refreshInterval.value)
})
</script>

<template>
  <div class="space-y-6">
    <SkeletonLoader v-if="statusFetch === 'pending'" variant="stat-grid" />
    <template v-else>
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">{{ $t('agents.title') }}</h1>
        <p class="text-sm text-gray-400">{{ $t('agents.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-3">
        <XpProgressBar
          v-if="gamification"
          :total-xp="gamification.totalXp"
          :level="gamification.level"
          :streak-days="gamification.streakDays"
        />
        <div class="flex items-center gap-2 text-xs">
          <span class="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span class="text-gray-500">{{ status?.tools_count }} {{ $t('agents.tools').toLowerCase() }}</span>
        </div>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refreshAll" />
      </div>
    </div>

    <!-- Emergency Alerts -->
    <EmergencyAlert v-if="recentAlerts.length" :alerts="recentAlerts" />

    <!-- Days Since Last Labs -->
    <NuxtLink
      v-if="daysSinceLastLabs != null && currentLevel === 0"
      to="/labs"
      class="flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors hover:bg-gray-800/30"
      :class="daysSinceLastLabs > 14 ? 'border-amber-500/30 bg-amber-500/5' : 'border-gray-800 bg-gray-900/50'"
    >
      <UIcon
        name="i-lucide-test-tube-diagonal"
        :class="daysSinceLastLabs > 14 ? 'text-amber-500' : 'text-teal-500'"
      />
      <div class="flex-1">
        <span class="text-sm text-white">{{ $t('agents.lastLabs') }}</span>
        <span class="text-xs text-gray-500 ml-2">
          {{ daysSinceLastLabs === 0 ? $t('agents.today') : $t('agents.daysAgo', { n: daysSinceLastLabs }) }}
        </span>
      </div>
      <UBadge
        v-if="daysSinceLastLabs > 14"
        color="warning"
        variant="subtle"
        size="xs"
      >{{ $t('agents.labsOverdue') }}</UBadge>
      <UIcon name="i-lucide-chevron-right" class="w-4 h-4 text-gray-600" />
    </NuxtLink>

    <!-- Autonomous Status + Budget Widget -->
    <div v-if="autonomous?.enabled && currentLevel === 0" class="rounded-xl border bg-gray-900/50 p-4 space-y-3" :class="costData?.budget_alert ? 'border-amber-600/50' : 'border-gray-800'">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <UIcon name="i-lucide-bot" class="text-teal-500 w-4 h-4" />
          <span class="text-sm font-medium text-white">{{ $t('agents.autonomous') }}</span>
          <UBadge color="success" variant="subtle" size="xs">{{ $t('common.active') }}</UBadge>
        </div>
        <UBadge v-if="costData?.budget_alert" color="warning" variant="subtle" size="xs">
          <UIcon name="i-lucide-alert-triangle" class="w-3 h-3 mr-1" />
          {{ $t('agents.budgetLow') }}
        </UBadge>
      </div>
      <!-- Budget stats row -->
      <div v-if="costData" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="text-center">
          <div class="text-xs text-gray-500">{{ $t('agents.todaySpend') }}</div>
          <div class="text-sm font-mono text-white">${{ costData.today_spend.toFixed(2) }}</div>
          <div class="text-[10px] text-gray-600">{{ $t('agents.capOf', { cap: costData.daily_cap.toFixed(0) }) }}</div>
        </div>
        <div class="text-center">
          <div class="text-xs text-gray-500">{{ $t('agents.mtdSpend') }}</div>
          <div class="text-sm font-mono text-white">${{ costData.mtd_spend.toFixed(2) }}</div>
          <div class="text-[10px] text-gray-600">{{ costData.month }}</div>
        </div>
        <div class="text-center">
          <div class="text-xs text-gray-500">{{ $t('agents.expectedEom') }}</div>
          <div class="text-sm font-mono text-white">${{ costData.expected_eom.toFixed(2) }}</div>
          <div class="text-[10px] text-gray-600">{{ $t('agents.projected') }}</div>
        </div>
        <div class="text-center">
          <div class="text-xs text-gray-500">{{ $t('agents.remainingCredit') }}</div>
          <div class="text-sm font-mono" :class="costData.budget_alert ? 'text-amber-400' : 'text-emerald-400'">${{ costData.remaining_credit.toFixed(2) }}</div>
          <div class="text-[10px] text-gray-600">~{{ costData.days_remaining }}d</div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ LEVEL 0: Room Grid ═══════════════ -->
    <Transition name="fade" mode="out-in">
      <div v-if="currentLevel === 0" key="grid">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <button
            v-for="room in rooms"
            :key="room.key"
            class="group relative rounded-xl border bg-gradient-to-br p-4 text-left transition-all hover:scale-[1.02] hover:shadow-lg cursor-pointer"
            :class="[room.color, room.border]"
            @click="openRoom(room)"
          >
            <!-- Status + new badge -->
            <div class="absolute top-3 right-3 flex items-center gap-1.5">
              <UBadge
                v-if="newCountForTools(room.tools) > 0"
                color="primary"
                variant="solid"
                size="xs"
              >
                {{ newCountForTools(room.tools) }}
              </UBadge>
              <span
                class="inline-block w-2.5 h-2.5 rounded-full"
                :class="{
                  'bg-green-500 animate-pulse': room.status === 'active',
                  'bg-yellow-500': room.status === 'recent',
                  'bg-gray-600': room.status === 'idle',
                }"
                :title="statusLabel(room.status)"
              />
            </div>

            <!-- Room header -->
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-lg bg-gray-800/60 flex items-center justify-center">
                <UIcon :name="room.icon" class="w-5 h-5 text-gray-300" />
              </div>
              <div>
                <div class="font-semibold text-white text-sm">{{ room.name }}</div>
                <div class="text-xs text-gray-500">{{ room.desc }}</div>
              </div>
            </div>

            <!-- Summary stats -->
            <div class="flex items-center gap-3 mt-3 text-[10px] text-gray-500">
              <span>{{ room.tools.length }} {{ $t('agents.workers').toLowerCase() }}</span>
              <span v-if="room.totalCalls > 0">{{ $t('agents.calls', { count: room.totalCalls }) }}</span>
              <span v-if="room.autonomousJobs.length > 0" class="flex items-center gap-0.5">
                <UIcon name="i-lucide-timer" class="w-2.5 h-2.5" />
                {{ room.autonomousJobs.length }}
              </span>
            </div>
          </button>
        </div>
      </div>

      <!-- ═══════════════ LEVEL 1: Room → Workers ═══════════════ -->
      <div v-else-if="currentLevel === 1 && selectedRoom" key="room">
        <!-- Breadcrumb -->
        <div class="flex items-center gap-2 mb-4">
          <button class="text-xs text-gray-500 hover:text-white transition-colors flex items-center gap-1" @click="goToGrid">
            <UIcon name="i-lucide-arrow-left" class="w-3 h-3" />
            {{ $t('agents.backToRooms') }}
          </button>
        </div>

        <!-- Room header -->
        <div class="rounded-xl border bg-gradient-to-br p-5 mb-5" :class="[selectedRoom.color, selectedRoom.border]">
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-xl bg-gray-800/60 flex items-center justify-center">
              <UIcon :name="selectedRoom.icon" class="w-6 h-6 text-gray-200" />
            </div>
            <div>
              <h2 class="text-lg font-bold text-white">{{ selectedRoom.name }}</h2>
              <p class="text-sm text-gray-400">{{ selectedRoom.desc }}</p>
            </div>
            <div class="ml-auto flex items-center gap-2">
              <span class="text-xs text-gray-500">{{ statusLabel(selectedRoom.status) }}</span>
              <span
                class="inline-block w-3 h-3 rounded-full"
                :class="{
                  'bg-green-500 animate-pulse': selectedRoom.status === 'active',
                  'bg-yellow-500': selectedRoom.status === 'recent',
                  'bg-gray-600': selectedRoom.status === 'idle',
                }"
              />
            </div>
          </div>
        </div>

        <!-- Workers grid -->
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ $t('agents.workers') }}</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-5">
          <button
            v-for="tool in selectedRoom.tools"
            :key="tool"
            class="rounded-xl border border-gray-800 bg-gray-900/50 p-4 text-left hover:border-gray-600 hover:bg-gray-800/50 transition-all cursor-pointer group"
            @click="openWorker(tool)"
          >
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-white group-hover:text-teal-400 transition-colors">
                {{ toolLabel(tool) }}
              </span>
              <div class="flex items-center gap-1.5">
                <UBadge
                  v-if="newCountForTools([tool]) > 0"
                  color="primary"
                  variant="solid"
                  size="xs"
                >
                  {{ newCountForTools([tool]) }}
                </UBadge>
                <span
                  class="inline-block w-2 h-2 rounded-full"
                  :class="{
                    'bg-green-500 animate-pulse': getAgentStatus([tool]) === 'active',
                    'bg-yellow-500': getAgentStatus([tool]) === 'recent',
                    'bg-gray-600': getAgentStatus([tool]) === 'idle',
                  }"
                />
              </div>
            </div>
            <div class="text-xs text-gray-500 space-y-0.5">
              <div v-if="toolStatsMap.get(tool)">
                {{ $t('agents.calls', { count: toolStatsMap.get(tool)!.count }) }}
              </div>
              <div v-if="lastActivityFor(tool)">
                {{ $t('agents.lastActive', { time: relativeTime(lastActivityFor(tool)!.timestamp) }) }}
              </div>
              <div v-else class="text-gray-600">
                {{ $t('agents.neverRun') }}
              </div>
            </div>
            <div v-for="job in toolJobsMap.get(tool) || []" :key="job.id"
                 class="flex items-center gap-1 text-[10px] text-gray-500 mt-1">
              <UIcon name="i-lucide-timer" class="w-2.5 h-2.5" />
              <span>{{ job.schedule }}</span>
            </div>
          </button>
        </div>

        <!-- Key Insights for this room -->
        <div v-if="roomInsights.length > 0" class="mt-5">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <UIcon name="i-lucide-sparkles" class="w-3 h-3 text-amber-500" />
            {{ $t('agents.keyInsights') }}
          </h3>
          <div class="rounded-xl border border-gray-800 bg-gray-900/50 divide-y divide-gray-800/50">
            <button
              v-for="(insight, i) in roomInsights"
              :key="i"
              class="w-full px-4 py-2.5 flex items-start gap-3 text-xs hover:bg-gray-800/30 transition-colors text-left"
              @click="openTaskDetail(insight.entry)"
            >
              <span class="text-gray-600 shrink-0 mt-0.5">{{ relativeTime(insight.timestamp) }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-gray-300">{{ insight.insight.line1 }}</div>
                <div v-if="insight.insight.line2" class="text-gray-500 mt-0.5">{{ insight.insight.line2 }}</div>
              </div>
              <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0 mt-0.5" />
            </button>
          </div>
        </div>

        <!-- Recent activity for this room -->
        <div v-if="roomEntries.length > 0" class="mt-5">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ $t('agents.activity') }}</h3>
          <div class="rounded-xl border border-gray-800 bg-gray-900/50 divide-y divide-gray-800/50">
            <button
              v-for="(entry, i) in roomEntries.slice(0, 10)"
              :key="i"
              class="w-full px-4 py-2.5 flex items-center gap-3 text-sm hover:bg-gray-800/30 transition-colors text-left"
              @click="openTaskDetail(entry)"
            >
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                :class="entry.status === 'ok' ? 'bg-green-500' : 'bg-red-500'"
              />
              <span class="text-xs text-gray-300 min-w-32">{{ toolLabel(entry.tool) }}</span>
              <span v-if="entry.output" class="text-xs text-gray-500 truncate max-w-64">{{ entry.output }}</span>
              <span class="text-gray-600 text-xs ml-auto shrink-0">{{ relativeTime(entry.timestamp) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- ═══════════════ LEVEL 2: Worker → Task History ═══════════════ -->
      <div v-else-if="currentLevel === 2 && selectedRoom && selectedWorker" key="worker">
        <!-- Breadcrumb -->
        <div class="flex items-center gap-1.5 text-xs text-gray-500 mb-4">
          <button class="hover:text-white transition-colors" @click="goToGrid">
            {{ $t('agents.breadcrumbRooms') }}
          </button>
          <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700" />
          <button class="hover:text-white transition-colors" @click="goBack">
            {{ selectedRoom.name }}
          </button>
          <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700" />
          <span class="text-teal-400">{{ toolLabel(selectedWorker) }}</span>
        </div>

        <!-- Worker header -->
        <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-5 mb-5">
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 rounded-lg bg-gray-800/60 flex items-center justify-center">
              <UIcon :name="selectedRoom.icon" class="w-5 h-5 text-gray-300" />
            </div>
            <div>
              <h2 class="text-lg font-bold text-white">{{ toolLabel(selectedWorker) }}</h2>
              <div class="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                <span v-if="toolStatsMap.get(selectedWorker)">
                  {{ $t('agents.calls', { count: toolStatsMap.get(selectedWorker)!.count }) }}
                </span>
                <span v-if="lastActivityFor(selectedWorker)">
                  {{ $t('agents.lastActive', { time: relativeTime(lastActivityFor(selectedWorker)!.timestamp) }) }}
                </span>
              </div>
            </div>
            <div class="ml-auto">
              <span
                class="inline-block w-3 h-3 rounded-full"
                :class="{
                  'bg-green-500 animate-pulse': getAgentStatus([selectedWorker]) === 'active',
                  'bg-yellow-500': getAgentStatus([selectedWorker]) === 'recent',
                  'bg-gray-600': getAgentStatus([selectedWorker]) === 'idle',
                }"
              />
            </div>
          </div>
        </div>

        <!-- Assigned scheduled jobs -->
        <div v-if="workerJobs.length" class="mb-5">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            {{ $t('agents.scheduledJobs') }}
          </h3>
          <div v-for="job in workerJobs" :key="job.id"
               class="rounded-lg border border-gray-800 bg-gray-900/30 px-4 py-3 mb-2">
            <div class="text-sm text-gray-300">{{ job.description }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ job.schedule }}</div>
          </div>
        </div>

        <!-- Key Insights for this worker -->
        <div v-if="workerInsights.length > 0" class="mb-5">
          <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <UIcon name="i-lucide-sparkles" class="w-3 h-3 text-amber-500" />
            {{ $t('agents.keyInsights') }}
          </h3>
          <div class="rounded-xl border border-gray-800 bg-gray-900/50 divide-y divide-gray-800/50">
            <button
              v-for="(insight, i) in workerInsights"
              :key="i"
              class="w-full px-4 py-2.5 flex items-start gap-3 text-xs hover:bg-gray-800/30 transition-colors text-left"
              @click="openTaskDetail(insight.entry)"
            >
              <span class="text-gray-600 shrink-0 mt-0.5">{{ relativeTime(insight.timestamp) }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-gray-300">{{ insight.insight.line1 }}</div>
                <div v-if="insight.insight.line2" class="text-gray-500 mt-0.5">{{ insight.insight.line2 }}</div>
              </div>
              <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0 mt-0.5" />
            </button>
          </div>
        </div>

        <!-- Task history -->
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ $t('agents.taskHistory') }}</h3>

        <div v-if="workerEntries.length > 0" class="space-y-2">
          <button
            v-for="(entry, i) in workerEntries"
            :key="i"
            class="w-full rounded-xl border border-gray-800 bg-gray-900/50 p-4 text-left hover:border-gray-600 hover:bg-gray-800/50 transition-all cursor-pointer"
            @click="openTaskDetail(entry)"
          >
            <div class="flex items-center gap-3 mb-2">
              <span
                class="w-2 h-2 rounded-full shrink-0"
                :class="entry.status === 'ok' ? 'bg-green-500' : 'bg-red-500'"
              />
              <span class="text-xs text-gray-400">
                {{ new Date(entry.timestamp).toLocaleString(
                  $i18n.locale === 'sk' ? 'sk-SK' : 'en-US',
                  { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
                ) }}
              </span>
              <span v-if="entry.duration_ms" class="text-[10px] text-gray-600">
                {{ $t('agents.durationLabel', { ms: entry.duration_ms }) }}
              </span>
              <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 ml-auto" />
            </div>

            <!-- Input -->
            <div v-if="entry.input" class="text-xs mb-1">
              <span class="text-gray-500">{{ $t('agents.inputLabel') }}:</span>
              <span class="text-gray-400 ml-1">{{ entry.input.length > 120 ? entry.input.slice(0, 120) + '...' : entry.input }}</span>
            </div>

            <!-- Output or Error -->
            <div v-if="entry.error" class="text-xs">
              <span class="text-red-500">{{ $t('agents.errorLabel') }}:</span>
              <span class="text-red-400 ml-1">{{ entry.error.length > 120 ? entry.error.slice(0, 120) + '...' : entry.error }}</span>
            </div>
            <div v-else-if="entry.output" class="text-xs">
              <span class="text-gray-500">{{ $t('agents.outputLabel') }}:</span>
              <span class="text-gray-400 ml-1">{{ entry.output.length > 120 ? entry.output.slice(0, 120) + '...' : entry.output }}</span>
            </div>
          </button>
        </div>

        <div v-else class="text-center py-12 text-sm text-gray-600">
          {{ $t('agents.noHistory') }}
        </div>
      </div>
    </Transition>
    </template>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
