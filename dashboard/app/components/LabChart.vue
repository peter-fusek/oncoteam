<script setup lang="ts">
import { Line } from 'vue-chartjs'

const props = defineProps<{
  title: string
  labels: string[]
  values: (number | null)[]
  thresholdMin?: number
  thresholdLabel?: string
  referenceMin?: number
  referenceMax?: number
  color?: string
  unit?: string
}>()

const chartData = computed(() => {
  const datasets: any[] = [
    {
      label: props.title,
      data: props.values,
      borderColor: props.color || '#14b8a6',
      backgroundColor: (props.color || '#14b8a6') + '20',
      tension: 0.3,
      fill: false,
      pointRadius: 4,
      pointHoverRadius: 6,
    },
  ]
  if (props.referenceMin != null && props.referenceMax != null) {
    datasets.push({
      label: 'Reference range',
      data: props.labels.map(() => props.referenceMax),
      borderColor: 'transparent',
      backgroundColor: '#14b8a610',
      fill: true,
      pointRadius: 0,
    })
    datasets.push({
      label: '',
      data: props.labels.map(() => props.referenceMin),
      borderColor: '#14b8a630',
      borderDash: [4, 4],
      backgroundColor: '#09090b',
      fill: true,
      pointRadius: 0,
    })
  }
  if (props.thresholdMin != null) {
    datasets.push({
      label: props.thresholdLabel || 'Threshold',
      data: props.labels.map(() => props.thresholdMin),
      borderColor: '#ef444480',
      borderDash: [6, 4],
      pointRadius: 0,
      fill: false,
    })
  }
  return { labels: props.labels, datasets }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: true, labels: { color: '#9ca3af', boxWidth: 12, font: { size: 11 } } },
  },
  scales: {
    x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: '#1f2937' } },
    y: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: '#1f2937' } },
  },
}
</script>

<template>
  <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-white">{{ title }}</h3>
      <span v-if="unit" class="text-xs text-gray-500">{{ unit }}</span>
    </div>
    <div class="h-48">
      <Line v-if="values.some(v => v != null)" :data="chartData" :options="chartOptions" />
      <div v-else class="flex items-center justify-center h-full text-xs text-gray-600">
        No data
      </div>
    </div>
  </div>
</template>
