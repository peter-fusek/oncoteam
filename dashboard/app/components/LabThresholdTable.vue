<script setup lang="ts">
defineProps<{
  thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; note?: string; action: string }>
}>()
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs text-gray-500 border-b border-gray-800">
          <th class="pb-2 pr-4">Parameter</th>
          <th class="pb-2 pr-4">Threshold</th>
          <th class="pb-2 pr-4">Note</th>
          <th class="pb-2">Action</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-800/50">
        <tr v-for="(t, name) in thresholds" :key="name" class="text-gray-300">
          <td class="py-2 pr-4 font-mono text-white">{{ name }}</td>
          <td class="py-2 pr-4">
            <template v-if="t.min">
              >= {{ t.min.toLocaleString() }} {{ t.unit || '' }}
            </template>
            <template v-else-if="t.max_ratio">
              &lt;= {{ t.max_ratio }}x ULN
            </template>
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
