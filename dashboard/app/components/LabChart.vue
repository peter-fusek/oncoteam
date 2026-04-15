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
  healthDirection?: string // 'lower_is_better' | 'higher_is_better' | 'in_range'
  cycleDates?: Array<{ date: string; label: string }> | null
}>()

// Custom plugin: draw vertical dashed lines for cycle dates
const cycleLinePlugin = {
  id: 'cycleLines',
  afterDraw(chart: any) {
    if (!props.cycleDates?.length) return
    const ctx = chart.ctx
    const xScale = chart.scales.x
    const yScale = chart.scales.y
    const labels = chart.data.labels || []

    for (const cycle of props.cycleDates) {
      const idx = labels.indexOf(cycle.date)
      if (idx < 0) continue
      const x = xScale.getPixelForValue(idx)
      ctx.save()
      ctx.beginPath()
      ctx.setLineDash([3, 3])
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.35)'
      ctx.lineWidth = 1
      ctx.moveTo(x, yScale.top)
      ctx.lineTo(x, yScale.bottom)
      ctx.stroke()
      // Label at top
      ctx.fillStyle = 'rgba(99, 102, 241, 0.7)'
      ctx.font = '8px DM Sans'
      ctx.textAlign = 'center'
      ctx.fillText(cycle.label, x, yScale.top - 3)
      ctx.restore()
    }
  },
}

const chartData = computed(() => {
  const datasets: any[] = []

  // Reference range band (green zone)
  if (props.referenceMin != null && props.referenceMax != null) {
    datasets.push({
      label: 'Reference max',
      data: props.labels.map(() => props.referenceMax),
      borderColor: 'rgba(16, 185, 129, 0.15)',
      borderWidth: 1,
      backgroundColor: 'transparent',
      fill: false,
      pointRadius: 0,
      datalabels: { display: false },
    })
    datasets.push({
      label: 'Reference min',
      data: props.labels.map(() => props.referenceMin),
      borderColor: 'rgba(16, 185, 129, 0.15)',
      borderWidth: 1,
      borderDash: [4, 4],
      backgroundColor: 'rgba(16, 185, 129, 0.06)',
      fill: '-1',
      pointRadius: 0,
      datalabels: { display: false },
    })
  }

  // Safety threshold line (red dashed)
  if (props.thresholdMin != null) {
    datasets.push({
      label: props.thresholdLabel || 'Threshold',
      data: props.labels.map(() => props.thresholdMin),
      borderColor: 'rgba(220, 38, 38, 0.45)',
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      datalabels: { display: false },
    })
  }

  // Main data line
  const mainColor = props.color || '#0d9488'
  datasets.push({
    label: props.title,
    data: props.values,
    borderColor: mainColor,
    backgroundColor: mainColor + '15',
    tension: 0.3,
    fill: false,
    spanGaps: true,
    pointRadius: 5,
    pointHoverRadius: 7,
    pointBorderWidth: 2,
    pointBorderColor: '#ffffff',
    pointBackgroundColor: props.values.map((v) => {
      if (v == null) return 'transparent'
      if (props.referenceMax != null && v > props.referenceMax) return '#dc2626'
      if (props.referenceMin != null && v < props.referenceMin) return '#d97706'
      if (props.thresholdMin != null && v < props.thresholdMin) return '#dc2626'
      return mainColor
    }),
    // Point shape: circle for normal, triangle for out-of-range
    pointStyle: props.values.map((v) => {
      if (v == null) return 'circle'
      if (props.thresholdMin != null && v < props.thresholdMin) return 'triangle'
      if (props.referenceMax != null && v > props.referenceMax) return 'triangle'
      if (props.referenceMin != null && v < props.referenceMin) return 'rectRot'
      return 'circle'
    }),
    datalabels: {
      display: (ctx: any) => {
        const idx = ctx.dataIndex
        const val = ctx.dataset.data[idx]
        if (val == null) return false
        const nonNullIndices = ctx.dataset.data
          .map((v: any, i: number) => v != null ? i : -1)
          .filter((i: number) => i >= 0)
        if (!nonNullIndices.length) return false
        if (idx === nonNullIndices[0] || idx === nonNullIndices[nonNullIndices.length - 1]) return true
        if (props.thresholdMin != null && val < props.thresholdMin) return true
        if (props.referenceMax != null && val > props.referenceMax) return true
        return false
      },
      color: (ctx: any) => {
        const val = ctx.dataset.data[ctx.dataIndex]
        if (val == null) return '#9ca3af'
        if (props.referenceMax != null && val > props.referenceMax) return '#dc2626'
        if (props.thresholdMin != null && val < props.thresholdMin) return '#dc2626'
        if (props.referenceMin != null && val < props.referenceMin) return '#d97706'
        return '#374151'
      },
      anchor: 'end' as const,
      align: (ctx: any) => {
        const idx = ctx.dataIndex
        const data = ctx.dataset.data
        const yPixel = ctx.chart.scales.y.getPixelForValue(data[idx])
        // Alternate top/bottom for adjacent labeled points to avoid overlap
        const nonNullIndices = data.map((v: any, i: number) => v != null ? i : -1).filter((i: number) => i >= 0)
        const labelIdx = nonNullIndices.indexOf(idx)
        if (yPixel < 40) return 'bottom'
        if (labelIdx > 0 && labelIdx % 2 === 1) return 'bottom'
        return 'top'
      },
      offset: 6,
      clamp: true,
      padding: 2,
      font: { size: 9, weight: 'bold' as const, family: 'DM Sans' },
      formatter: (val: number) => {
        if (val == null) return ''
        if (Math.abs(val) >= 100_000) return `${(val / 1000).toFixed(0)}k`
        if (Math.abs(val) >= 10_000) return `${(val / 1000).toFixed(1)}k`
        if (Math.abs(val) >= 1_000) return val.toLocaleString()
        return String(val)
      },
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
        color: '#6b7280',
        boxWidth: 10,
        boxHeight: 10,
        font: { size: 10, family: 'DM Sans' },
        filter: (item: any) => item.text === props.title || item.text === (props.thresholdLabel || 'Threshold'),
      },
    },
    tooltip: {
      backgroundColor: '#1f2937',
      titleFont: { family: 'DM Sans', size: 11 },
      bodyFont: { family: 'DM Sans', size: 12 },
      padding: 10,
      cornerRadius: 8,
      callbacks: {
        label: (ctx: any) => {
          const val = ctx.parsed.y
          if (val == null) return ''
          let label = `${props.title}: ${val.toLocaleString()}`
          if (props.unit) label += ` ${props.unit}`
          return label
        },
      },
    },
    datalabels: {},
  },
  scales: {
    x: {
      ticks: { color: '#6b7280', font: { size: 9, family: 'DM Sans' }, maxRotation: 45, autoSkip: true, maxTicksLimit: 8 },
      grid: { color: '#f3f4f6' },
      border: { color: '#e5e7eb' },
    },
    y: {
      ticks: { color: '#6b7280', font: { size: 10, family: 'DM Sans' } },
      grid: { color: '#f3f4f6' },
      border: { color: '#e5e7eb' },
    },
  },
}))

// Determine trend summary
const trendSummary = computed(() => {
  const nonNull = props.values.filter((v): v is number => v != null && typeof v === 'number' && isFinite(v))
  if (nonNull.length < 2) return null
  const last = nonNull[nonNull.length - 1]
  const prev = nonNull[nonNull.length - 2]
  if (prev === 0) return { direction: last > 0 ? 'up' : 'stable' as const, pctChange: '—', last }
  const pctChange = ((last - prev) / prev) * 100
  if (!isFinite(pctChange)) return null
  return {
    direction: last > prev ? 'up' : last < prev ? 'down' : 'stable',
    pctChange: Math.abs(pctChange).toFixed(1),
    last,
  }
})
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-4 hover:shadow-sm transition-shadow">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <h3 class="text-sm font-semibold text-gray-900">{{ title }}</h3>
        <!-- Trend indicator -->
        <span
          v-if="trendSummary"
          class="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full"
          :class="{
            'bg-green-50 text-green-700': trendSummary.direction === 'down' && healthDirection === 'lower_is_better' || trendSummary.direction === 'up' && healthDirection === 'higher_is_better',
            'bg-red-50 text-red-700': trendSummary.direction === 'up' && healthDirection === 'lower_is_better' || trendSummary.direction === 'down' && healthDirection === 'higher_is_better',
            'bg-gray-100 text-gray-600': trendSummary.direction === 'stable' || !healthDirection || healthDirection === 'in_range',
          }"
        >
          <span v-if="trendSummary.direction === 'up'">&#8593;</span>
          <span v-else-if="trendSummary.direction === 'down'">&#8595;</span>
          <span v-else>&#8594;</span>
          {{ trendSummary.pctChange }}%
        </span>
      </div>
      <span v-if="unit" class="text-[10px] text-gray-400 font-medium uppercase tracking-wide">{{ unit }}</span>
    </div>
    <div class="h-48">
      <Line v-if="values.some(v => v != null)" :data="chartData" :options="chartOptions" :plugins="[cycleLinePlugin]" />
      <div v-else class="flex items-center justify-center h-full text-xs text-gray-400">
        No data available
      </div>
    </div>
  </div>
</template>
