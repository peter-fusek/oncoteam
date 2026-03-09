<script setup lang="ts">
defineProps<{
  alerts: Array<{
    param: string
    value: number
    threshold: number
    action: string
    date?: string
  }>
}>()

// Critical thresholds (immediate attention needed)
function isCritical(param: string, value: number): boolean {
  const criticals: Record<string, number> = {
    ANC: 500,
    PLT: 25000,
  }
  return param in criticals && value < criticals[param]
}
</script>

<template>
  <div v-if="alerts.length" class="rounded-xl border-2 p-4 animate-pulse"
    :class="alerts.some(a => isCritical(a.param, a.value))
      ? 'border-red-500 bg-red-500/10'
      : 'border-amber-500 bg-amber-500/10'"
  >
    <div class="flex items-center gap-2 mb-2">
      <UIcon
        :name="alerts.some(a => isCritical(a.param, a.value)) ? 'i-lucide-siren' : 'i-lucide-triangle-alert'"
        :class="alerts.some(a => isCritical(a.param, a.value)) ? 'text-red-500' : 'text-amber-500'"
        class="w-5 h-5"
      />
      <span class="font-bold text-sm"
        :class="alerts.some(a => isCritical(a.param, a.value)) ? 'text-red-400' : 'text-amber-400'"
      >
        {{ alerts.some(a => isCritical(a.param, a.value)) ? $t('components.emergency.title') : $t('labs.safetyAlerts') }}
      </span>
    </div>
    <div class="space-y-1">
      <div v-for="(alert, i) in alerts" :key="i" class="flex items-center gap-2 text-sm">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :class="isCritical(alert.param, alert.value) ? 'bg-red-500' : 'bg-amber-500'"
        />
        <span class="font-mono text-white">{{ alert.param }}</span>
        <span class="text-gray-400">= {{ alert.value.toLocaleString() }}</span>
        <span class="text-gray-600">(min: {{ alert.threshold.toLocaleString() }})</span>
        <UBadge
          :color="isCritical(alert.param, alert.value) ? 'error' : 'warning'"
          variant="subtle"
          size="xs"
        >
          {{ isCritical(alert.param, alert.value) ? $t('components.emergency.critical') : alert.action }}
        </UBadge>
        <span v-if="alert.date" class="text-xs text-gray-600 ml-auto">{{ alert.date }}</span>
      </div>
    </div>
    <div v-if="alerts.some(a => isCritical(a.param, a.value))" class="mt-2 text-xs text-red-400">
      {{ $t('components.emergency.immediateAttention') }}
    </div>
  </div>
</template>
