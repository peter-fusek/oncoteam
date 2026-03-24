<script setup lang="ts">
// Prompts merged into Agents page (#135) — redirect for backward compat
await navigateTo('/agents', { redirectCode: 301 })

const { t, locale } = useI18n()
const { fetchApi } = useOncoteamApi()

// Fetch all agents
const { data: agentsData } = fetchApi<{
  agents: Array<{ id: string; name: string; category: string; model: string; last_run: string | null }>
}>('/agents', { lazy: true })

const agents = computed(() => agentsData.value?.agents || [])

// Filter state
const selectedAgent = ref<string>('')
const allRuns = ref<Array<any>>([])
const loading = ref(false)
const expandedRunId = ref<number | null>(null)

// Fetch runs for selected agent (or all agents)
async function fetchRuns() {
  loading.value = true
  allRuns.value = []

  try {
    if (selectedAgent.value) {
      // Single agent — use per-agent endpoint
      const data = await $fetch(`/api/oncoteam/agents/${selectedAgent.value}/runs?limit=50&lang=${locale.value}`, {
        timeout: 8000,
      })
      allRuns.value = (data as any)?.runs || []
    } else {
      // All agents — single aggregated MCP call
      const data = await $fetch(`/api/oncoteam/agent-runs?limit=50&lang=${locale.value}`, {
        timeout: 20000,
      })
      allRuns.value = (data as any)?.runs || []
    }
  } catch {
    allRuns.value = []
  }

  // Sort by timestamp descending
  allRuns.value.sort((a: any, b: any) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime())
  loading.value = false
}

// Fetch on mount and when filter changes
watch([selectedAgent, agents], () => {
  if (agents.value.length > 0) fetchRuns()
}, { immediate: true })

const showMessages = ref<Record<number, boolean>>({})

function toggleRun(id: number) {
  expandedRunId.value = expandedRunId.value === id ? null : id
}

const { timeAgo, formatDuration, formatCost } = useAgentFormatters()
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">Prompt Explorer</h1>
        <p class="text-sm text-gray-500">Full transparency into every autonomous agent prompt, response, and tool interaction</p>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="flex items-center gap-3">
      <select
        v-model="selectedAgent"
        class="bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700 focus:border-teal-500 focus:outline-none"
      >
        <option value="">All agents</option>
        <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name || a.id }}</option>
      </select>
      <span class="text-xs text-gray-500">{{ allRuns.length }} runs</span>
      <button
        class="text-xs text-teal-700 hover:text-teal-600 transition-colors"
        @click="fetchRuns"
      >
        Refresh
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-500 py-8 text-center">Loading runs...</div>

    <!-- Empty -->
    <div v-else-if="allRuns.length === 0" class="text-sm text-gray-500 py-8 text-center">
      No runs found. Autonomous agents store traces when they run.
    </div>

    <!-- Run list -->
    <div v-else class="space-y-2">
      <div
        v-for="run in allRuns"
        :key="run.id"
        class="rounded-lg border border-gray-200 bg-white overflow-hidden"
      >
        <!-- Run header -->
        <button
          class="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
          @click="toggleRun(run.id)"
        >
          <div class="flex items-center gap-3">
            <span :class="run.error ? 'text-red-600' : 'text-teal-700'" class="text-xs font-mono">
              {{ run.error ? 'ERR' : 'OK' }}
            </span>
            <span class="text-sm font-medium text-gray-900">{{ run.task_name }}</span>
            <span class="text-sm text-gray-500">{{ timeAgo(run.timestamp) }}</span>
          </div>
          <div class="flex items-center gap-3 text-xs text-gray-500">
            <span v-if="run.turns">{{ run.turns }}T</span>
            <span>{{ run.tool_calls?.length || 0 }} tools</span>
            <span>{{ formatDuration(run.duration_ms) }}</span>
            <span>{{ formatCost(run.cost) }}</span>
            <UIcon
              name="i-lucide-chevron-down"
              class="w-4 h-4 transition-transform"
              :class="{ 'rotate-180': expandedRunId === run.id }"
            />
          </div>
        </button>

        <!-- Expanded detail -->
        <div v-if="expandedRunId === run.id" class="border-t border-gray-200 px-4 py-3 space-y-3">
          <!-- Meta row -->
          <div class="flex flex-wrap gap-4 text-xs text-gray-500">
            <span>{{ run.input_tokens?.toLocaleString() }} in / {{ run.output_tokens?.toLocaleString() }} out</span>
            <span>{{ formatCost(run.cost) }}</span>
            <span v-if="run.started_at">Started: {{ new Date(run.started_at).toLocaleString() }}</span>
            <span v-if="run.completed_at">Completed: {{ new Date(run.completed_at).toLocaleString() }}</span>
          </div>

          <!-- Prompt -->
          <div v-if="run.prompt">
            <p class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Prompt Sent</p>
            <div class="text-xs text-gray-700 bg-blue-50 border border-blue-200 rounded p-2 max-h-60 overflow-y-auto font-mono whitespace-pre-wrap">
              {{ run.prompt }}
            </div>
          </div>

          <!-- Thinking -->
          <div v-if="run.thinking?.length">
            <p class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Thinking ({{ run.thinking.length }})</p>
            <div
              v-for="(thought, i) in run.thinking"
              :key="i"
              class="text-xs text-gray-500 bg-[var(--clinical-bg)] rounded p-2 max-h-40 overflow-y-auto font-mono whitespace-pre-wrap mb-1"
            >
              {{ thought }}
            </div>
          </div>

          <!-- Tool calls with I/O -->
          <div v-if="run.tool_calls?.length">
            <p class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Tool Calls ({{ run.tool_calls.length }})</p>
            <div v-for="(tc, i) in run.tool_calls" :key="i" class="rounded border border-gray-200 bg-[var(--clinical-bg)] overflow-hidden mb-1">
              <div class="px-2 py-1 text-xs font-mono border-b border-gray-200 flex items-center gap-2">
                <span class="text-teal-700 font-semibold">{{ tc.tool }}</span>
                <span class="text-gray-500">{{ JSON.stringify(tc.input).slice(0, 120) }}{{ JSON.stringify(tc.input).length > 120 ? '...' : '' }}</span>
              </div>
              <div v-if="tc.output" class="px-2 py-1 text-xs text-gray-500 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                {{ tc.output }}
                <span v-if="tc.has_full_output" class="text-yellow-500 text-[10px]"> [truncated]</span>
              </div>
            </div>
          </div>

          <!-- Message History (collapsible) -->
          <div v-if="run.messages?.length > 1">
            <button class="flex items-center gap-1 text-[10px] text-gray-500 uppercase tracking-wider hover:text-gray-700" @click="showMessages[run.id] = !showMessages[run.id]">
              <UIcon name="i-lucide-chevron-right" class="w-3 h-3 transition-transform" :class="{ 'rotate-90': showMessages[run.id] }" />
              Message History ({{ run.messages.length }} messages)
            </button>
            <div v-if="showMessages[run.id]" class="mt-1 space-y-1">
              <div v-for="(msg, mi) in run.messages" :key="mi" class="text-xs rounded p-2 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto" :class="msg.role === 'user' ? 'bg-blue-50 text-blue-700' : 'bg-[var(--clinical-bg)] text-gray-500'">
                <span class="text-[10px] uppercase font-semibold" :class="msg.role === 'user' ? 'text-blue-600' : 'text-gray-500'">{{ msg.role }}</span>
                {{ typeof msg.content === 'string' ? msg.content.slice(0, 500) : JSON.stringify(msg.content).slice(0, 500) }}
              </div>
            </div>
          </div>

          <!-- Response -->
          <div v-if="run.response">
            <p class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Response</p>
            <div class="text-xs text-gray-700 bg-[var(--clinical-bg)] rounded p-2 max-h-60 overflow-y-auto whitespace-pre-wrap">
              {{ run.response }}
            </div>
          </div>

          <!-- Error -->
          <div v-if="run.error" class="text-xs text-red-600 bg-red-50 rounded p-2">
            {{ run.error }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
