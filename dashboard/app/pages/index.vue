<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { t } = useI18n()
const { formatDate } = useFormatDate()

const { data: status, refresh: refreshStatus } = await fetchApi<{
  status: string
  version: string
  session_id: string
  tools_count: number
}>('/status')

const { data: stats, refresh: refreshStats } = await fetchApi<{
  stats: Array<{ tool_name: string; status: string; count: number; avg_duration_ms: number }>
}>('/stats')

const { data: activity, refresh: refreshActivity } = await fetchApi<{
  entries: Array<{ tool: string; status: string; duration_ms: number; timestamp: string }>
  total: number
}>('/activity?limit=15')

const { data: autonomous, refresh: refreshAutonomous } = await fetchApi<{
  enabled: boolean
  daily_cost: number
  jobs?: Array<{ id: string; schedule: string; description: string }>
  job_count?: number
}>('/autonomous')

const { data: gamification, refresh: refreshGamification } = useFetch<{
  totalXp: number
  level: string
  streakDays: number
}>('/api/gamification')

const { data: labData, refresh: refreshLabs } = await fetchApi<{
  entries: Array<{
    date: string
    alerts: Array<{ param: string; value: number; threshold: number; action: string }>
  }>
}>('/labs?limit=3')

function toolLabel(toolName: string): string {
  const key = `agents.toolNames.${toolName}`
  const label = t(key)
  // If no translation found, t() returns the key — fall back to formatted name
  return label === key ? toolName.replace(/_/g, ' ') : label
}

// Map tools to rooms
const rooms = computed(() => {
  const toolStats = new Map(
    (stats.value?.stats ?? []).map(s => [s.tool_name, s])
  )

  return [
    {
      name: t('agents.rooms.researchLab'),
      desc: t('agents.rooms.researchLabDesc'),
      icon: 'i-lucide-flask-conical',
      color: 'from-blue-500/20 to-blue-600/10',
      border: 'border-blue-500/30',
      statusColor: 'bg-blue-500',
      tools: ['search_pubmed', 'search_clinical_trials', 'search_clinical_trials_adjacent'],
      autonomousJobs: ['daily_research', 'trial_monitor'],
      status: getAgentStatus(['search_pubmed', 'search_clinical_trials', 'search_clinical_trials_adjacent']),
    },
    {
      name: t('agents.rooms.eligibilityCheck'),
      desc: t('agents.rooms.eligibilityCheckDesc'),
      icon: 'i-lucide-target',
      color: 'from-amber-500/20 to-amber-600/10',
      border: 'border-amber-500/30',
      statusColor: 'bg-amber-500',
      tools: ['check_trial_eligibility', 'fetch_trial_details', 'fetch_pubmed_article'],
      autonomousJobs: [],
      status: getAgentStatus(['check_trial_eligibility', 'fetch_trial_details', 'fetch_pubmed_article']),
    },
    {
      name: t('agents.rooms.clinicalProtocol'),
      desc: t('agents.rooms.clinicalProtocolDesc'),
      icon: 'i-lucide-shield-check',
      color: 'from-red-500/20 to-red-600/10',
      border: 'border-red-500/30',
      statusColor: 'bg-red-500',
      tools: ['pre_cycle_check', 'tumor_marker_review', 'response_assessment'],
      autonomousJobs: ['pre_cycle_check', 'tumor_marker_review', 'response_assessment'],
      status: getAgentStatus(['pre_cycle_check', 'tumor_marker_review', 'response_assessment']),
    },
    {
      name: t('agents.rooms.analyticsRoom'),
      desc: t('agents.rooms.analyticsRoomDesc'),
      icon: 'i-lucide-bar-chart-3',
      color: 'from-purple-500/20 to-purple-600/10',
      border: 'border-purple-500/30',
      statusColor: 'bg-purple-500',
      tools: ['analyze_labs', 'compare_labs', 'get_lab_trends'],
      autonomousJobs: [],
      status: getAgentStatus(['analyze_labs', 'compare_labs', 'get_lab_trends']),
    },
    {
      name: t('agents.rooms.reportRoom'),
      desc: t('agents.rooms.reportRoomDesc'),
      icon: 'i-lucide-file-text',
      color: 'from-green-500/20 to-green-600/10',
      border: 'border-green-500/30',
      statusColor: 'bg-green-500',
      tools: ['daily_briefing', 'summarize_session', 'review_session'],
      autonomousJobs: ['weekly_briefing', 'mtb_preparation'],
      status: getAgentStatus(['daily_briefing', 'summarize_session', 'review_session']),
    },
    {
      name: t('agents.rooms.documentVault'),
      desc: t('agents.rooms.documentVaultDesc'),
      icon: 'i-lucide-archive',
      color: 'from-cyan-500/20 to-cyan-600/10',
      border: 'border-cyan-500/30',
      statusColor: 'bg-cyan-500',
      tools: ['search_documents', 'view_document', 'get_patient_context'],
      autonomousJobs: ['file_scan'],
      status: getAgentStatus(['search_documents', 'view_document', 'get_patient_context']),
    },
    {
      name: t('agents.rooms.sessionLog'),
      desc: t('agents.rooms.sessionLogDesc'),
      icon: 'i-lucide-notebook-pen',
      color: 'from-rose-500/20 to-rose-600/10',
      border: 'border-rose-500/30',
      statusColor: 'bg-rose-500',
      tools: ['log_research_decision', 'log_session_note', 'create_improvement_issue'],
      autonomousJobs: [],
      status: getAgentStatus(['log_research_decision', 'log_session_note', 'create_improvement_issue']),
    },
  ].map(room => ({
    ...room,
    totalCalls: room.tools.reduce((sum, t) => sum + (toolStats.get(t)?.count ?? 0), 0),
  }))
})

function getAgentStatus(tools: string[]) {
  const recent = activity.value?.entries ?? []
  const lastActivity = recent.find(e => tools.includes(e.tool))
  if (!lastActivity) return 'idle'
  const age = Date.now() - new Date(lastActivity.timestamp).getTime()
  if (age < 5 * 60_000) return 'active'
  if (age < 60 * 60_000) return 'recent'
  return 'idle'
}

function statusLabel(status: string) {
  if (status === 'active') return t('agents.statusActive')
  if (status === 'recent') return t('agents.statusRecent')
  return t('agents.statusIdle')
}

const drilldown = useDrilldown()

const totalCalls = computed(() =>
  (stats.value?.stats ?? []).reduce((sum, s) => sum + s.count, 0)
)

const recentAlerts = computed(() => {
  if (!labData.value?.entries) return []
  return labData.value.entries
    .filter(e => e.alerts?.length)
    .flatMap(e => e.alerts.map(a => ({ ...a, date: e.date })))
})

async function refreshAll() {
  await Promise.all([refreshStatus(), refreshStats(), refreshActivity(), refreshAutonomous(), refreshGamification(), refreshLabs()])
}

// Auto-refresh every 30 seconds
const refreshInterval = ref<ReturnType<typeof setInterval>>()
onMounted(() => {
  refreshInterval.value = setInterval(refreshAll, 30_000)
})
onUnmounted(() => {
  clearInterval(refreshInterval.value)
})
</script>

<template>
  <div class="space-y-6">
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

    <!-- Autonomous Agent Status -->
    <div v-if="autonomous" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <UIcon name="i-lucide-bot" class="text-teal-500 w-5 h-5" />
          <span class="font-semibold text-sm text-white">{{ $t('agents.autonomous') }}</span>
          <UBadge
            :color="autonomous.enabled ? 'success' : 'neutral'"
            variant="subtle"
            size="xs"
          >
            {{ autonomous.enabled ? $t('common.active') : $t('common.disabled') }}
          </UBadge>
        </div>
        <span v-if="autonomous.daily_cost > 0" class="text-xs text-gray-400">
          {{ $t('agents.costToday', { cost: autonomous.daily_cost.toFixed(4) }) }}
        </span>
      </div>
      <div v-if="autonomous.jobs?.length" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        <div
          v-for="job in autonomous.jobs"
          :key="job.id"
          class="rounded-lg bg-gray-800/50 px-3 py-2"
        >
          <div class="text-xs font-medium text-gray-300">{{ job.description }}</div>
          <div class="text-[10px] text-gray-500 mt-0.5">{{ job.schedule }}</div>
        </div>
      </div>
    </div>

    <!-- Agent Rooms Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="room in rooms"
        :key="room.name"
        class="group relative rounded-xl border bg-gradient-to-br p-4 transition-all hover:scale-[1.02]"
        :class="[room.color, room.border]"
      >
        <!-- Status indicator -->
        <div class="absolute top-3 right-3 flex items-center gap-1.5">
          <span class="text-[10px] text-gray-500">{{ statusLabel(room.status) }}</span>
          <span
            class="inline-block w-2.5 h-2.5 rounded-full"
            :class="{
              'bg-green-500 animate-pulse': room.status === 'active',
              'bg-yellow-500': room.status === 'recent',
              'bg-gray-600': room.status === 'idle',
            }"
          />
        </div>

        <!-- Room header -->
        <div class="flex items-center gap-3 mb-2">
          <div class="w-8 h-8 rounded-lg bg-gray-800/60 flex items-center justify-center">
            <UIcon :name="room.icon" class="w-4 h-4 text-gray-300" />
          </div>
          <div>
            <div class="font-semibold text-white text-sm">{{ room.name }}</div>
            <div class="text-xs text-gray-500">{{ room.desc }}</div>
          </div>
        </div>

        <!-- Tools list with human names -->
        <div class="space-y-1 mt-3">
          <div
            v-for="tool in room.tools"
            :key="tool"
            class="text-xs text-gray-400 flex items-center gap-1.5"
          >
            <span class="w-1 h-1 rounded-full shrink-0" :class="room.statusColor" />
            {{ toolLabel(tool) }}
          </div>
        </div>

        <!-- Autonomous badge -->
        <div v-if="room.autonomousJobs.length > 0" class="mt-3 pt-2 border-t border-gray-800/50">
          <div class="flex items-center gap-1 text-[10px] text-gray-500">
            <UIcon name="i-lucide-timer" class="w-3 h-3" />
            {{ $t('agents.scheduledTasks') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Activity Feed -->
    <div class="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div class="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <UIcon name="i-lucide-activity" class="text-gray-400" />
          <span class="font-semibold text-sm text-white">{{ $t('agents.activity') }}</span>
        </div>
        <UBadge variant="subtle" size="xs" color="neutral">
          {{ $t('agents.operationsCompleted', { count: totalCalls }) }}
        </UBadge>
      </div>
      <div v-if="activity?.entries?.length" class="divide-y divide-gray-800/50">
        <div
          v-for="(entry, i) in activity.entries"
          :key="i"
          class="px-4 py-2 flex items-center gap-3 text-sm hover:bg-gray-800/30 transition-colors"
        >
          <span
            class="w-1.5 h-1.5 rounded-full shrink-0"
            :class="entry.status === 'ok' ? 'bg-green-500' : 'bg-red-500'"
          />
          <span class="text-xs text-gray-300 min-w-40">{{ toolLabel(entry.tool) }}</span>
          <span class="text-gray-600 text-xs ml-auto">
            {{ new Date(entry.timestamp).toLocaleString(
              $i18n.locale === 'sk' ? 'sk-SK' : 'en-US',
              { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
            ) }}
          </span>
        </div>
      </div>
      <div v-else class="px-4 py-8 text-center text-gray-600 text-sm">
        {{ $t('agents.noActivity') }}
      </div>
    </div>
  </div>
</template>
