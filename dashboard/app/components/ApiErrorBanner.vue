<template>
  <div
    v-if="error || degradedActive"
    :class="[
      'rounded-lg border p-3 text-sm flex items-center gap-2',
      degradedActive && !error
        ? 'border-amber-400/40 bg-amber-50 text-amber-800'
        : 'border-red-500/30 bg-red-500/5 text-red-600',
    ]"
  >
    <UIcon
      :name="degradedActive && !error ? 'i-lucide-activity' : 'i-lucide-alert-triangle'"
      class="shrink-0"
    />
    <span class="flex-1">
      <template v-if="error">{{ $t('components.apiError') }}</template>
      <template v-else>
        <!-- Half-open state: "Reconnecting…" only. Countdown is irrelevant while
             the upstream is probing, and showing both reads noisy. -->
        <template v-if="breakerState === 'half_open'">
          {{ $t('components.apiDegradedHalfOpen') }}
        </template>
        <template v-else>
          {{ $t('components.apiDegraded') }}
          <span v-if="cooldownSeconds > 0" class="ml-1">
            {{ $t('components.apiDegradedRetry', { seconds: Math.ceil(cooldownSeconds) }) }}
          </span>
        </template>
      </template>
    </span>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  error?: string | null
  degraded?: boolean
  cooldownSeconds?: number
}>()

// Auto-subscribe to global circuit breaker state when `degraded` prop is
// not passed in — lets bare <ApiErrorBanner /> placements work without
// every page wiring the composable manually.
const cb = useCircuitBreakerStatus()
const degradedActive = computed(() =>
  props.degraded !== undefined ? props.degraded : cb.degraded.value
)
const cooldownSeconds = computed(() =>
  props.cooldownSeconds !== undefined ? props.cooldownSeconds : cb.cooldownSeconds.value
)
const breakerState = computed(() => cb.state.value?.state ?? 'closed')
</script>
