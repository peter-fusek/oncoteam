interface CircuitBreakerState {
  state: 'open' | 'closed'
  cooldown_remaining_s: number
  consecutive_failures: number
  rss_backoff_active?: boolean
  rss_backoff_remaining_s?: number
}

interface DiagnosticsResponse {
  healthy: boolean
  circuit_breaker: CircuitBreakerState
}

// Degraded = breaker open OR RSS backoff active. Both mean oncofiles is
// stressed and dashboard data may be stale / partial. Keep this a separate
// composable (not inside useOncoteamApi) so the poll runs once globally.
export function useCircuitBreakerStatus() {
  const state = useState<CircuitBreakerState | null>('oncoteam:circuit-breaker', () => null)
  const fetchError = useState<Error | null>('oncoteam:circuit-breaker:error', () => null)
  const degraded = computed(() => {
    const s = state.value
    if (!s) return false
    return s.state === 'open' || !!s.rss_backoff_active
  })
  const cooldownSeconds = computed(() => {
    const s = state.value
    if (!s) return 0
    return Math.max(s.cooldown_remaining_s || 0, s.rss_backoff_remaining_s || 0)
  })

  async function refresh() {
    try {
      const res = await $fetch<DiagnosticsResponse>('/api/oncoteam/diagnostics')
      state.value = res.circuit_breaker
      fetchError.value = null
    } catch (e) {
      fetchError.value = e as Error
    }
  }

  let timer: ReturnType<typeof setInterval> | null = null
  function start(intervalMs = 30000) {
    if (timer) return
    refresh()
    timer = setInterval(refresh, intervalMs)
  }
  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  return { state, degraded, cooldownSeconds, refresh, start, stop, fetchError }
}
