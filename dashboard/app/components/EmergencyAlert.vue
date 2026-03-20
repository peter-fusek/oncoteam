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

// Human-readable action labels
const ACTION_LABELS: Record<string, string> = {
  hold_chemo: 'Hold Chemotherapy',
  dose_reduce: 'Reduce Dose',
  monitor: 'Monitor Closely',
  transfuse: 'Consider Transfusion',
  urgent: 'Urgent Review',
}
function actionLabel(action: string): string {
  return ACTION_LABELS[action] || action.replace(/_/g, ' ')
}
</script>

<template>
  <div v-if="alerts.length" class="rounded-xl border-2 p-4 animate-pulse"
    :class="alerts.some(a => isCritical(a.param, a.value))
      ? 'border-red-400 bg-red-50'
      : 'border-amber-400 bg-amber-50'"
  >
    <div class="flex items-center gap-2 mb-2">
      <UIcon
        :name="alerts.some(a => isCritical(a.param, a.value)) ? 'i-lucide-siren' : 'i-lucide-triangle-alert'"
        :class="alerts.some(a => isCritical(a.param, a.value)) ? 'text-red-600' : 'text-amber-600'"
        class="w-5 h-5"
      />
      <span class="font-bold text-sm"
        :class="alerts.some(a => isCritical(a.param, a.value)) ? 'text-red-700' : 'text-amber-700'"
      >
        {{ alerts.some(a => isCritical(a.param, a.value)) ? $t('components.emergency.title') : $t('labs.safetyAlerts') }}
      </span>
    </div>
    <div class="space-y-1">
      <div v-for="(alert, i) in alerts" :key="i" class="flex items-center gap-2 text-sm">
        <UIcon
          :name="isCritical(alert.param, alert.value) ? 'i-lucide-circle-x' : 'i-lucide-alert-triangle'"
          class="w-3.5 h-3.5 shrink-0"
          :class="isCritical(alert.param, alert.value) ? 'text-red-500' : 'text-amber-500'"
        />
        <NuxtLink :to="`/dictionary?q=${alert.param}`" class="font-mono text-gray-900 hover:text-teal-700 underline decoration-dotted">{{ alert.param }}</NuxtLink>
        <span class="text-gray-600">= {{ Number(alert.value).toLocaleString('en-US', { maximumFractionDigits: 1 }) }}</span>
        <span class="text-gray-400">(min: {{ Number(alert.threshold).toLocaleString('en-US', { maximumFractionDigits: 0 }) }})</span>
        <UBadge
          :color="isCritical(alert.param, alert.value) ? 'error' : 'warning'"
          variant="subtle"
          size="xs"
        >
          {{ isCritical(alert.param, alert.value) ? $t('components.emergency.critical') : actionLabel(alert.action) }}
        </UBadge>
        <span v-if="alert.date" class="text-xs text-gray-400 ml-auto">{{ alert.date }}</span>
      </div>
    </div>
    <div v-if="alerts.some(a => isCritical(a.param, a.value))" class="mt-2 text-xs text-red-600 font-medium">
      {{ $t('components.emergency.immediateAttention') }}
    </div>
  </div>
</template>
