<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: diag, status: diagStatus } = fetchApi<{
  circuit_breaker?: { state: string; failures?: number; oncofiles_rss_mb?: number; rss_backoff_active?: boolean; total_rss_backoffs?: number; rss_history?: Array<{ ts: number; mb: number }> }
  oncofiles_reachable?: boolean
  suppressed_errors?: Array<{ context: string; timestamp: string }>
  document_counts?: { total: number; with_ocr: number; with_ai: number }
}>('/diagnostics', { lazy: true, server: false })

const { data: health } = fetchApi<{
  status: string
  version: string
  tools_count: number
}>('/status', { lazy: true, server: false })

const cbState = computed(() => diag.value?.circuit_breaker?.state ?? 'unknown')
const rssMb = computed(() => diag.value?.circuit_breaker?.oncofiles_rss_mb ?? 0)
const rssHistory = computed(() => diag.value?.circuit_breaker?.rss_history ?? [])
const totalBackoffs = computed(() => diag.value?.circuit_breaker?.total_rss_backoffs ?? 0)

// SVG sparkline path from RSS history
const sparklinePath = computed(() => {
  const points = rssHistory.value
  if (points.length < 2) return ''
  const maxMb = Math.max(...points.map((p: { mb: number }) => p.mb), 200)
  const w = 200
  const h = 40
  return points.map((p: { mb: number }, i: number) => {
    const x = (i / (points.length - 1)) * w
    const y = h - (p.mb / maxMb) * h
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})
const reachable = computed(() => diag.value?.oncofiles_reachable ?? null)
const recentErrors = computed(() => (diag.value?.suppressed_errors ?? []).slice(0, 10))
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Oncofiles</h1>
        <p class="text-sm text-gray-500">Document management backend status</p>
      </div>
      <a href="https://oncofiles.com/dashboard" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5">
        <UButton icon="i-lucide-external-link" variant="soft" size="xs" color="primary">
          Open Oncofiles Dashboard
        </UButton>
      </a>
    </div>

    <SkeletonLoader v-if="diagStatus === 'pending'" variant="cards" />

    <!-- Status cards -->
    <div v-if="diag" class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <!-- Circuit Breaker -->
      <div class="rounded-xl border bg-white p-4" :class="cbState === 'open' ? 'border-red-300 bg-red-50' : 'border-gray-200'">
        <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Circuit Breaker</div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full" :class="cbState === 'closed' ? 'bg-green-500' : cbState === 'open' ? 'bg-red-500 animate-pulse' : 'bg-gray-400'" />
          <span class="text-lg font-bold" :class="cbState === 'open' ? 'text-red-700' : 'text-gray-900'">{{ cbState }}</span>
        </div>
      </div>

      <!-- RSS Memory -->
      <div class="rounded-xl border bg-white p-4" :class="rssMb >= 400 ? 'border-amber-300 bg-amber-50' : 'border-gray-200'">
        <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Memory (RSS)</div>
        <div class="text-lg font-bold" :class="rssMb >= 400 ? 'text-amber-700' : 'text-gray-900'">{{ rssMb.toFixed(0) }} MB</div>
        <div class="text-xs text-gray-400">{{ rssMb >= 450 ? 'Backoff active (2min)' : rssMb >= 400 ? 'Backoff active (30s)' : 'Normal' }}</div>
        <svg v-if="sparklinePath" class="mt-2 w-full h-10" viewBox="0 0 200 40" preserveAspectRatio="none">
          <line x1="0" y1="32" x2="200" y2="32" stroke="#fbbf24" stroke-width="0.5" stroke-dasharray="2,2" />
          <path :d="sparklinePath" fill="none" :stroke="rssMb >= 400 ? '#d97706' : '#10b981'" stroke-width="1.5" />
        </svg>
        <div v-if="totalBackoffs > 0" class="text-xs text-amber-600 mt-1">{{ totalBackoffs }} backoff{{ totalBackoffs > 1 ? 's' : '' }} since restart</div>
      </div>

      <!-- Reachability -->
      <div class="rounded-xl border border-gray-200 bg-white p-4">
        <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Reachable</div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full" :class="reachable === true ? 'bg-green-500' : reachable === false ? 'bg-red-500' : 'bg-gray-400'" />
          <span class="text-lg font-bold text-gray-900">{{ reachable === true ? 'Yes' : reachable === false ? 'No' : 'Checking...' }}</span>
        </div>
      </div>
    </div>

    <!-- Oncoteam backend info -->
    <div v-if="health" class="rounded-xl border border-gray-200 bg-white p-4">
      <div class="text-xs text-gray-500 uppercase tracking-wider mb-2">Oncoteam Backend</div>
      <div class="flex items-center gap-4 text-sm text-gray-700">
        <span>Status: <strong :class="health.status === 'ok' ? 'text-green-700' : 'text-red-700'">{{ health.status }}</strong></span>
        <span>Version: <strong>{{ health.version }}</strong></span>
        <span>Tools: <strong>{{ health.tools_count }}</strong></span>
      </div>
    </div>

    <!-- Recent errors -->
    <div v-if="recentErrors.length" class="rounded-xl border border-gray-200 bg-white p-4">
      <div class="text-xs text-gray-500 uppercase tracking-wider mb-3">Recent Suppressed Errors ({{ recentErrors.length }})</div>
      <div class="space-y-1 max-h-64 overflow-y-auto">
        <div v-for="(err, i) in recentErrors" :key="i" class="flex items-start gap-2 text-xs text-gray-600 py-1 border-b border-gray-50 last:border-0">
          <span class="text-gray-400 font-mono shrink-0 w-28">{{ err.timestamp?.slice(11, 19) }}</span>
          <span class="text-gray-700">{{ err.context }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
