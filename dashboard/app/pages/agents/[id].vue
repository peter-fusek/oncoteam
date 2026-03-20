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
const systemPrompt = computed(() => configData.value?.system_prompt || '')
const showSystemPrompt = ref(false)
const showMessages = ref<Record<number, boolean>>({})

// Fetch run history
const { data: runsData, status: runsStatus } = fetchApi<{
  runs: Array<{
    id: number; timestamp: string; task_name: string; model: string
    cost: number; duration_ms: number; input_tokens: number; output_tokens: number
    tool_calls: Array<{ tool: string; input: any; output: string; has_full_output: boolean }>
    thinking: string[]; response: string; prompt: string; error: string | null
    messages: Array<{ role: string; content: any }>
    turns: number; started_at: string | null; completed_at: string | null
  }>
}>(`/agents/${agentId.value}/runs?limit=20`, { lazy: true })

const runs = computed(() => runsData.value?.runs || [])

// Expanded run for detail view
const expandedRunId = ref<number | null>(null)
function toggleRun(id: number) {
  expandedRunId.value = expandedRunId.value === id ? null : id
}

const { timeAgo, formatDuration, formatCost } = useAgentFormatters()

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
      <NuxtLink to="/" class="text-gray-500 hover:text-gray-900 transition-colors">
        <UIcon name="i-lucide-arrow-left" class="w-5 h-5" />
      </NuxtLink>
      <div v-if="agent">
        <h1 class="text-xl font-bold text-gray-900">{{ agent.name }}</h1>
        <p class="text-sm text-gray-500">{{ agent.description }}</p>
      </div>
      <div v-else>
        <h1 class="text-xl font-bold text-gray-900">Agent: {{ agentId }}</h1>
      </div>
    </div>

    <!-- Config cards -->
    <div v-if="agent" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="rounded-lg border border-gray-200 bg-white p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Model</p>
        <p class="text-sm font-medium text-gray-900 mt-1">{{ modelLabels[agent.model] || agent.model }}</p>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Schedule</p>
        <p class="text-sm font-medium text-gray-900 mt-1">{{ agent.schedule }}</p>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Last Run</p>
        <p class="text-sm font-medium text-gray-900 mt-1">{{ agent.last_run ? timeAgo(agent.last_run) : 'Never' }}</p>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3">
        <p class="text-[10px] text-gray-500 uppercase tracking-wider">Category</p>
        <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium" :class="categoryColors[agent.category] || 'bg-gray-500/20 text-gray-500'">
          {{ agent.category }}
        </span>
      </div>
    </div>

    <!-- System Prompt (collapsible) -->
    <div v-if="systemPrompt">
      <button class="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-2 hover:text-gray-900 transition-colors" @click="showSystemPrompt = !showSystemPrompt">
        <UIcon name="i-lucide-chevron-down" class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showSystemPrompt }" />
        System Prompt
        <span class="text-gray-500 font-normal text-xs">({{ systemPrompt.length.toLocaleString() }} chars)</span>
      </button>
      <div v-if="showSystemPrompt" class="rounded-lg border border-gray-200 bg-[var(--clinical-bg)] p-4 overflow-x-auto max-h-96 overflow-y-auto">
        <pre class="text-xs text-gray-700 font-mono whitespace-pre-wrap">{{ systemPrompt }}</pre>
      </div>
    </div>

    <!-- Prompt Template -->
    <div v-if="promptTemplate">
      <h2 class="text-sm font-semibold text-gray-700 mb-2">
        Task Prompt Template
        <span v-if="isDynamicPrompt" class="text-gray-500 font-normal text-xs ml-2">
          (variables injected at runtime)
        </span>
      </h2>
      <div class="rounded-lg border border-gray-200 bg-[var(--clinical-bg)] p-4 overflow-x-auto max-h-80 overflow-y-auto">
        <pre class="text-xs text-gray-700 font-mono whitespace-pre-wrap">{{ promptTemplate }}</pre>
      </div>
    </div>

    <!-- Run History -->
    <div>
      <h2 class="text-sm font-semibold text-gray-700 mb-3">
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
          class="rounded-lg border border-gray-200 bg-white overflow-hidden"
        >
          <!-- Run header (clickable) -->
          <button
            class="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
            @click="toggleRun(run.id)"
          >
            <div class="flex items-center gap-3">
              <span :class="run.error ? 'text-red-600' : 'text-teal-700'" class="text-xs font-mono">
                {{ run.error ? 'ERR' : 'OK' }}
              </span>
              <span class="text-sm text-gray-700">{{ timeAgo(run.timestamp) }}</span>
              <span class="text-xs text-gray-500">{{ formatDuration(run.duration_ms) }}</span>
            </div>
            <div class="flex items-center gap-3 text-xs text-gray-500">
              <span v-if="run.turns">{{ run.turns }} turns</span>
              <span>{{ run.tool_calls?.length || 0 }} tools</span>
              <span>{{ formatCost(run.cost) }}</span>
              <span class="text-gray-500">{{ run.model === 'light' ? 'H' : 'S' }}</span>
              <UIcon
                name="i-lucide-chevron-down"
                class="w-4 h-4 transition-transform"
                :class="{ 'rotate-180': expandedRunId === run.id }"
              />
            </div>
          </button>

          <!-- Expanded detail -->
          <div v-if="expandedRunId === run.id" class="border-t border-gray-200 px-4 py-3 space-y-3">
            <!-- Token counts -->
            <div class="flex gap-4 text-xs text-gray-500">
              <span>Input: {{ run.input_tokens?.toLocaleString() }} tokens</span>
              <span>Output: {{ run.output_tokens?.toLocaleString() }} tokens</span>
              <span>Cost: {{ formatCost(run.cost) }}</span>
            </div>

            <!-- Prompt (what was asked) -->
            <div v-if="run.prompt" class="space-y-1">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Prompt Sent</p>
              <div class="text-xs text-gray-700 bg-blue-50 border border-blue-200 rounded p-2 max-h-60 overflow-y-auto font-mono whitespace-pre-wrap">
                {{ run.prompt }}
              </div>
            </div>

            <!-- Thinking -->
            <div v-if="run.thinking?.length" class="space-y-1">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Thinking</p>
              <div
                v-for="(thought, i) in run.thinking"
                :key="i"
                class="text-xs text-gray-500 bg-[var(--clinical-bg)] rounded p-2 max-h-40 overflow-y-auto font-mono whitespace-pre-wrap"
              >
                {{ thought }}
              </div>
            </div>

            <!-- Tool calls with I/O -->
            <div v-if="run.tool_calls?.length" class="space-y-2">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Tool Calls ({{ run.tool_calls.length }})</p>
              <div v-for="(tc, i) in run.tool_calls" :key="i" class="rounded border border-gray-200 bg-[var(--clinical-bg)] overflow-hidden">
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

            <!-- Response -->
            <div v-if="run.response">
              <p class="text-[10px] text-gray-500 uppercase tracking-wider">Response</p>
              <div class="text-xs text-gray-700 bg-[var(--clinical-bg)] rounded p-2 max-h-60 overflow-y-auto whitespace-pre-wrap">
                {{ run.response }}
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

            <!-- Error -->
            <div v-if="run.error" class="text-xs text-red-600 bg-red-50 rounded p-2">
              {{ run.error }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
