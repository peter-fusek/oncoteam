/**
 * Circuit-breaker observer — reads oncofiles /readiness directly per the
 * oncofiles#469 + oncoteam#424 Task 3 contract. `cooldown_remaining_s`
 * is authoritative for the countdown; we decrement it locally between
 * polls so the banner reads like a real-time timer instead of a
 * stairstep.
 *
 * Previous implementation inferred state by counting 500s bounced off
 * /api/diagnostics — that's what produced the false-alarm banner when
 * oncofiles was closed/healthy.
 */

interface OncofilesBreaker {
  state: 'closed' | 'open' | 'half_open'
  failures_in_window?: number
  window_seconds?: number
  max_failures?: number
  cooldown_seconds?: number
  cooldown_remaining_s: number
  last_trip_at?: string | null
  last_trip_cause?: string | null
  trip_count_total?: number
}

interface OncofilesReadiness {
  status?: string
  version?: string
  db?: string
  memory_rss_mb?: number
  circuit_breaker?: OncofilesBreaker | null
  error?: string
}

export function useCircuitBreakerStatus() {
  const state = useState<OncofilesBreaker | null>('oncoteam:breaker:state', () => null)
  const fetchError = useState<Error | null>('oncoteam:breaker:error', () => null)
  const lastPolledAt = useState<number>('oncoteam:breaker:polledAt', () => 0)
  // Local 1s decrement so the countdown reads as a real timer between
  // poll ticks. Reset to cooldown_remaining_s on every successful poll.
  const localRemaining = useState<number>('oncoteam:breaker:localRemaining', () => 0)

  // #431 Step 4: degraded also fires when oncofiles is fully unreachable
  // (readiness proxy returns 502 or errors). Before this, `state.value=null`
  // from a 502 looked identical to a healthy closed breaker — dashboard
  // showed no banner during full outage while every downstream API call
  // failed. Now: degraded if breaker is open OR if the readiness probe
  // itself is failing.
  const degraded = computed(() => {
    if (fetchError.value) return true
    const s = state.value
    if (!s) return false
    return s.state !== 'closed'
  })

  // Surface the outage kind so the banner can show accurate copy:
  // "Database temporarily unavailable" (breaker open, known cooldown)
  // vs. "Oncofiles is offline" (can't reach readiness at all).
  const outageKind = computed<'breaker_open' | 'unreachable' | 'half_open' | null>(() => {
    if (fetchError.value) return 'unreachable'
    const s = state.value
    if (!s) return null
    if (s.state === 'half_open') return 'half_open'
    if (s.state === 'open') return 'breaker_open'
    return null
  })

  const cooldownSeconds = computed(() => Math.max(0, Math.ceil(localRemaining.value)))

  async function refresh() {
    try {
      const res = await $fetch<OncofilesReadiness>('/api/oncofiles-readiness')
      const cb = res?.circuit_breaker ?? null
      state.value = cb
      lastPolledAt.value = Date.now()
      localRemaining.value = cb?.cooldown_remaining_s ?? 0
      fetchError.value = null
    } catch (e) {
      // Distinguish "proxy up but breaker null" from "proxy itself failing".
      // The latter is a full-outage signal — we must surface it.
      state.value = null
      localRemaining.value = 0
      lastPolledAt.value = Date.now()
      fetchError.value = e as Error
    }
  }

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let countdownTimer: ReturnType<typeof setInterval> | null = null

  function start(intervalMs = 30000) {
    if (pollTimer) return
    refresh()
    pollTimer = setInterval(refresh, intervalMs)
    // 1s local decrement between polls so the countdown animates.
    countdownTimer = setInterval(() => {
      if (localRemaining.value > 0) localRemaining.value -= 1
    }, 1000)
  }

  function stop() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }

  return { state, degraded, outageKind, cooldownSeconds, refresh, start, stop, fetchError, lastPolledAt }
}
