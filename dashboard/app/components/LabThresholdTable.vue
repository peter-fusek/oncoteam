<script setup lang="ts">
defineProps<{
  thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; note?: string; action: string }>
  lastValues?: Record<string, { value: number; sample_date?: string; sync_date?: string; date?: string; status: 'safe' | 'warning' | 'critical' }>
}>()

defineEmits<{
  rowClick: [param: string]
}>()

const statusColors: Record<string, string> = {
  safe: 'bg-green-500/20 text-green-400',
  warning: 'bg-amber-500/20 text-amber-400',
  critical: 'bg-red-500/20 text-red-400',
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs text-gray-500 border-b border-gray-200">
          <th class="pb-2 pr-4">{{ $t('components.labThreshold.parameter') }}</th>
          <th class="pb-2 pr-4">{{ $t('components.labThreshold.threshold') }}</th>
          <th v-if="lastValues" class="pb-2 pr-4">{{ $t('components.labThreshold.lastValue') }}</th>
          <th v-if="lastValues" class="pb-2 pr-4">{{ $t('components.labThreshold.sampleDate') }}</th>
          <th class="pb-2 pr-4">{{ $t('components.labThreshold.note') }}</th>
          <th class="pb-2">{{ $t('components.labThreshold.action') }}</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        <tr
          v-for="(t, name) in thresholds"
          :key="name"
          class="text-gray-700 transition-colors"
          :class="lastValues ? 'cursor-pointer hover:bg-gray-50' : ''"
          @click="lastValues ? $emit('rowClick', String(name)) : undefined"
        >
          <td class="py-2 pr-4 font-mono text-gray-900">{{ name }}</td>
          <td class="py-2 pr-4">
            <template v-if="t.min">
              >= {{ t.min.toLocaleString() }} {{ t.unit || '' }}
            </template>
            <template v-else-if="t.max_ratio">
              &lt;= {{ t.max_ratio }}x ULN
            </template>
          </td>
          <td v-if="lastValues" class="py-2 pr-4">
            <template v-if="lastValues[String(name)]">
              <span class="font-mono">{{ lastValues[String(name)].value.toLocaleString() }}</span>
              <UBadge
                class="ml-1.5"
                variant="subtle"
                size="xs"
                :color="lastValues[String(name)].status === 'safe' ? 'success' : lastValues[String(name)].status === 'warning' ? 'warning' : 'error'"
              >
                {{ $t(`components.labThreshold.${lastValues[String(name)].status}`) }}
              </UBadge>
            </template>
            <span v-else class="text-gray-600 text-xs">{{ $t('components.labThreshold.noData') }}</span>
          </td>
          <td v-if="lastValues" class="py-2 pr-4 text-xs text-gray-500">
            <span :title="lastValues[String(name)]?.sync_date ? `${$t('components.labThreshold.syncDate')}: ${lastValues[String(name)]?.sync_date}` : ''">
              {{ lastValues[String(name)]?.sample_date || lastValues[String(name)]?.date || '-' }}
            </span>
          </td>
          <td class="py-2 pr-4 text-xs text-gray-500">{{ t.note || '-' }}</td>
          <td class="py-2">
            <UBadge variant="subtle" size="xs" :color="t.action === 'hold_chemo' ? 'error' : 'warning'">
              {{ t.action }}
            </UBadge>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
