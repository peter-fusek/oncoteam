<script setup lang="ts">
const route = useRoute()
const { t, locale } = useI18n()
const { fetchApi } = useOncoteamApi()

const agentId = computed(() => route.params.id as string)

// Fetch agent list to get this agent's config
const { data: agentsData } = fetchApi<{
  agents: Array<{
    id: string; name: string; description: string; category: string
    model: string; schedule: string; cooldown_hours: number; max_turns: number
    whatsapp_enabled: boolean; last_run: string | null; enabled: boolean
  }>
}>('/agents', { lazy: true })

const agent = computed(() =>
  agentsData.value?.agents?.find((a: any) => a.id === agentId.value),
)

// Fetch agent config (includes prompt_template)
const { data: configData } = fetchApi<{
  id: string; prompt_template: string
  [key: string]: any
}>(`/agents/${agentId.value}/config`, { lazy: true })

const promptTemplate = computed(() => configData.value?.prompt_template || '')
const isDynamicPrompt = computed(() => promptTemplate.value.startsWith('[Dynamic'))

// Fetch run history
const { data: runsData, status: runsStatus } = fetchApi<{
  runs: Array<{
    id: number; timestamp: string; task_name: string; model: string
    cost: number; duration_ms: number; input_tokens: number; output_tokens: number
    tool_calls: Array<{ tool: string; input: any }>
    thinking: string[]; response: string; error: string | null
  }>
}>(`/agents/${agentId.value}/runs?limit=20`, { lazy: true })

const runs = computed(() => runsData.value?.runs || [])

// Expanded run for detail view
const expandedRunId = ref<number | null>(null)
function toggleRun(id: number) {
  expandedRunId.value = expandedRunId.value === id ? null : id
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`
}

function timeAgo(ts: string): string {
  if (!ts) return '-'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const categoryColors: Record<string, string> = {
  data_pipeline: 'bg-blue-500/20 text-blue-400',
  research: 'bg-purple-500/20 text-purple-400',
  clinical: 'bg-red-500/20 text-red-400',
  reporting: 'bg-green-500/20 text-green-400',
}

const modelLabels: Record<string, string> = {
  light: 'Haiku',
  sonnet: 'Sonnet',
}
</script>

<template>
  <div class="space-y-6">
    <!-- Back + Header -->
    <div class="flex items-center gap-3">
      <NuxtLink to="/" class="text-gray-400 hover:text-white transition-colors">
        <UIcon name="i-lucide-arrow-left" class="w-5 h-5" />
      </NuxtLink>
      <div v-if="agent">
        <h1 class="text-xl font-bold text-white">{{ agent.name }}</h1>
        <p class="text-sm text-gray-400">{{ agent.description }}</p>
      </div>
      <div v-else>
        <h1 class="text-xl font-bold text-white">Agent: {{ agentId }}</h1>
      </div>
    </div>

    <!-- Config cards -->
    <div v-if="agent" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Model</p>
        <p class="text-sm font-medium text-white mt-1">{{ modelLabels[agent.model] || agent.model }}</p>
      </div>
      <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Schedule</p>
        <p class="text-sm font-medium text-white mt-1">{{ agent.schedule }}</p>
      </div>
      <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Last Run</p>
        <p class="text-sm font-medium text-white mt-1">{{ agent.last_run ? timeAgo(agent.last_run) : 'Never' }}</p>
      </div>
      <div class="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Category</p>
        <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium" :class="categoryColors[agent.category] || 'bg-gray-500/20 text-gray-400'">
          {{ agent.category }}
        </span>
      </div>
    </div>

    <!-- Prompt Template -->
    <div v-if="promptTemplate">
      <h2 class="text-sm font-semibold text-gray-300 mb-2">
        Prompt Template
        <span v-if="isDynamicPrompt" class="text-gray-500 font-normal text-xs ml-2">
          (variables injected at runtime)
        </span>
      </h2>
      <div class="rounded-lg border border-gray-800 bg-gray-950 p-4 overflow-x-auto max-h-80 overflow-y-auto">
        <pre class="text-xs text-gray-300 font-mono whitespace-pre-wrap">{{ promptTemplate }}</pre>
      </div>
    </div>

    <!-- Run History -->
    <div>
      <h2 class="text-sm font-semibold text-gray-300 mb-3">
        Run History
        <span class="text-gray-500 font-normal">({{ runs.length }} runs)</span>
      </h2>

      <div v-if="runsStatus === 'pending'" class="text-sm text-gray-500">Loading...</div>

      <div v-else-if="runs.length === 0" class="text-sm text-gray-500 py-8 text-center">
        No runs recorded yet. Traces are stored starting from this sprint.
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="run in runs"
          :key="run.id"
          class="rounded-lg border border-gray-800 bg-gray-900/50 overflow-hidden"
        >
          <!-- Run header (clickable) -->
          <button
            class="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors text-left"
            @click="toggleRun(run.id)"
          >
            <div class="flex items-center gap-3">
              <span :class="run.error ? 'text-red-400' : 'text-teal-400'" class="text-xs font-mono">
                {{ run.error ? 'ERR' : 'OK' }}
              </span>
              <span class="text-sm text-gray-300">{{ timeAgo(run.timestamp) }}</span>
              <span class="text-xs text-gray-500">{{ formatDuration(run.duration_ms) }}</span>
            </div>
            <div class="flex items-center gap-3 text-xs text-gray-500">
              <span>{{ run.tool_calls?.length || 0 }} tools</span>
              <span>{{ formatCost(run.cost) }}</span>
              <span class="text-gray-600">{{ run.model === 'light' ? 'H' : 'S' }}</span>
              <UIcon
                name="i-lucide-chevron-down"
                class="w-4 h-4 transition-transform"
                :class="{ 'rotate-180': expandedRunId === run.id }"
              />
            </div>
          </button>

          <!-- Expanded detail -->
          <div v-if="expandedRunId === run.id" class="border-t border-gray-800 px-4 py-3 space-y-3">
            <!-- Token counts -->
            <div class="flex gap-4 text-xs text-gray-500">
              <span>Input: {{ run.input_tokens?.toLocaleString() }} tokens</span>
              <span>Output: {{ run.output_tokens?.toLocaleString() }} tokens</span>
              <span>Cost: {{ formatCost(run.cost) }}</span>
            </div>

            <!-- Thinking -->
            <div v-if="run.thinking?.length" class="space-y-1">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Thinking</p>
              <div
                v-for="(thought, i) in run.thinking"
                :key="i"
                class="text-xs text-gray-400 bg-gray-950 rounded p-2 max-h-40 overflow-y-auto font-mono whitespace-pre-wrap"
              >
                {{ thought }}
              </div>
            </div>

            <!-- Tool calls -->
            <div v-if="run.tool_calls?.length" class="space-y-1">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Tool Calls ({{ run.tool_calls.length }})</p>
              <div class="space-y-1">
                <div
                  v-for="(tc, i) in run.tool_calls"
                  :key="i"
                  class="text-xs text-gray-400 bg-gray-950 rounded px-2 py-1 font-mono"
                >
                  <span class="text-teal-400">{{ tc.tool }}</span>({{ JSON.stringify(tc.input).slice(0, 100) }}{{ JSON.stringify(tc.input).length > 100 ? '...' : '' }})
                </div>
              </div>
            </div>

            <!-- Response -->
            <div v-if="run.response">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Response</p>
              <div class="text-xs text-gray-300 bg-gray-950 rounded p-2 max-h-60 overflow-y-auto whitespace-pre-wrap">
                {{ run.response }}
              </div>
            </div>

            <!-- Error -->
            <div v-if="run.error" class="text-xs text-red-400 bg-red-950/30 rounded p-2">
              {{ run.error }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
