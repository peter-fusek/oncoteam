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
  const datasets: any[] = []

  // Reference range max line (top of band) — must come before min for fill between
  if (props.referenceMin != null && props.referenceMax != null) {
    datasets.push({
      label: 'Reference max',
      data: props.labels.map(() => props.referenceMax),
      borderColor: '#14b8a620',
      borderWidth: 1,
      backgroundColor: 'transparent',
      fill: false,
      pointRadius: 0,
      datalabels: { display: false },
    })
    // Reference range min line — fills UP to max (index 0)
    datasets.push({
      label: 'Reference min',
      data: props.labels.map(() => props.referenceMin),
      borderColor: '#14b8a620',
      borderWidth: 1,
      borderDash: [4, 4],
      backgroundColor: '#14b8a610',
      fill: '-1',
      pointRadius: 0,
      datalabels: { display: false },
    })
  }

  // Safety threshold line
  if (props.thresholdMin != null) {
    datasets.push({
      label: props.thresholdLabel || 'Threshold',
      data: props.labels.map(() => props.thresholdMin),
      borderColor: '#ef444460',
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      datalabels: { display: false },
    })
  }

  // Main data line — always last so it renders on top
  datasets.push({
    label: props.title,
    data: props.values,
    borderColor: props.color || '#14b8a6',
    backgroundColor: (props.color || '#14b8a6') + '20',
    tension: 0.3,
    fill: false,
    spanGaps: true,
    pointRadius: 4,
    pointHoverRadius: 6,
    pointBackgroundColor: props.values.map((v) => {
      if (v == null) return 'transparent'
      if (props.referenceMax != null && v > props.referenceMax) return '#ef4444'
      if (props.referenceMin != null && v < props.referenceMin) return '#f59e0b'
      if (props.thresholdMin != null && v < props.thresholdMin) return '#ef4444'
      return props.color || '#14b8a6'
    }),
    datalabels: {
      display: (ctx: any) => {
        // Show labels on first, last, and out-of-range points
        const idx = ctx.dataIndex
        const val = ctx.dataset.data[idx]
        if (val == null) return false
        const len = ctx.dataset.data.filter((v: any) => v != null).length
        if (len <= 4) return true
        if (idx === 0 || idx === ctx.dataset.data.length - 1) return true
        if (props.referenceMax != null && val > props.referenceMax) return true
        if (props.referenceMin != null && val < props.referenceMin) return true
        if (props.thresholdMin != null && val < props.thresholdMin) return true
        return false
      },
      color: (ctx: any) => {
        const val = ctx.dataset.data[ctx.dataIndex]
        if (val == null) return '#9ca3af'
        if (props.referenceMax != null && val > props.referenceMax) return '#ef4444'
        if (props.thresholdMin != null && val < props.thresholdMin) return '#ef4444'
        if (props.referenceMin != null && val < props.referenceMin) return '#f59e0b'
        return '#d1d5db'
      },
      anchor: 'end' as const,
      align: 'top' as const,
      font: { size: 10, weight: 'bold' as const },
      formatter: (val: number) => val?.toLocaleString() ?? '',
    },
  })

  return { labels: props.labels, datasets }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: true,
      labels: {
        color: '#9ca3af',
        boxWidth: 12,
        font: { size: 11 },
        filter: (item: any) => item.text === props.title || item.text === (props.thresholdLabel || 'Threshold'),
      },
    },
    datalabels: {},
  },
  scales: {
    x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: '#1f2937' } },
    y: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: '#1f2937' } },
  },
}))
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
