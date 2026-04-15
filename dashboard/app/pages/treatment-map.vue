<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()
const drilldown = useDrilldown()

// Fetch all data in parallel
const { data: timeline, status: timelineStatus, error: timelineError, refresh } = fetchApi<{
  events: Array<{
    id: number
    event_date: string
    event_type: string
    title: string
    notes: string
  }>
  total: number
  error?: string
}>('/timeline?limit=500', { lazy: true, server: false })

const { data: labs } = fetchApi<{
  entries: Array<{
    id: number
    date: string
    values: Record<string, number>
  }>
}>('/labs?limit=50', { lazy: true, server: false })

const { data: protocol } = fetchApi<{
  current_cycle: number
  milestones: Array<{ cycle: number; action: string; description: string }>
}>('/protocol', { lazy: true, server: false })

// ── Time axis computation ──────────────────────────────
const timeRange = computed(() => {
  if (!timeline.value?.events?.length) return null
  const dates = timeline.value.events
    .map(e => e.event_date)
    .filter(Boolean)
    .sort()
  if (!dates.length) return null
  const first = new Date(dates[0] + 'T00:00:00')
  const last = new Date(dates[dates.length - 1] + 'T00:00:00')
  // Pad: 1 month before first, 1 month after last
  const start = new Date(first.getFullYear(), first.getMonth() - 1, 1)
  const end = new Date(last.getFullYear(), last.getMonth() + 2, 0)
  return { start, end }
})

const months = computed(() => {
  if (!timeRange.value) return []
  const { start, end } = timeRange.value
  const result: Array<{ date: Date; label: string; shortLabel: string }> = []
  const cur = new Date(start.getFullYear(), start.getMonth(), 1)
  while (cur <= end) {
    result.push({
      date: new Date(cur),
      label: cur.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
      shortLabel: cur.toLocaleDateString('en-US', { month: 'short' }),
    })
    cur.setMonth(cur.getMonth() + 1)
  }
  return result
})

function dateToPercent(dateStr: string): number {
  if (!timeRange.value || !dateStr) return 0
  const d = new Date(dateStr + 'T00:00:00')
  const { start, end } = timeRange.value
  const total = end.getTime() - start.getTime()
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, ((d.getTime() - start.getTime()) / total) * 100))
}

// ── Track data ─────────────────────────────────────────
const CHEMO_TYPES = new Set(['chemo_cycle', 'chemo', 'chemotherapy'])
const EVENT_TYPES = new Set(['surgery', 'scan', 'consultation', 'imaging'])
const LAB_TYPES = new Set(['lab_work', 'lab_result', 'labs'])

interface TrackEvent {
  id: number
  date: string
  title: string
  type: string
  notes: string
  left: number
  width: number
}

const chemoEvents = computed<TrackEvent[]>(() => {
  if (!timeline.value?.events) return []
  const events = timeline.value.events
    .filter(e => CHEMO_TYPES.has(e.event_type) && e.event_date)
    .sort((a, b) => a.event_date.localeCompare(b.event_date))
  return events.map(e => ({
    id: e.id,
    date: e.event_date,
    title: e.title,
    type: e.event_type,
    notes: e.notes,
    left: dateToPercent(e.event_date),
    width: 2.5, // ~14 days block
  }))
})

const supportEvents = computed<TrackEvent[]>(() => {
  if (!timeline.value?.events) return []
  return timeline.value.events
    .filter(e => e.event_type === 'medication_log' && e.event_date)
    .map(e => ({
      id: e.id,
      date: e.event_date,
      title: e.title,
      type: e.event_type,
      notes: e.notes,
      left: dateToPercent(e.event_date),
      width: 0,
    }))
})

const clinicalEvents = computed<TrackEvent[]>(() => {
  if (!timeline.value?.events) return []
  return timeline.value.events
    .filter(e => EVENT_TYPES.has(e.event_type) && e.event_date)
    .map(e => ({
      id: e.id,
      date: e.event_date,
      title: e.title,
      type: e.event_type,
      notes: e.notes,
      left: dateToPercent(e.event_date),
      width: 0,
    }))
})

// ── Tumor marker sparkline data ────────────────────────
const markerData = computed(() => {
  if (!labs.value?.entries?.length) return null
  const entries = [...labs.value.entries].sort((a, b) => a.date.localeCompare(b.date))
  const ceaPoints: Array<{ date: string; value: number; left: number }> = []
  const ca199Points: Array<{ date: string; value: number; left: number }> = []
  for (const entry of entries) {
    if (entry.values?.CEA != null) {
      ceaPoints.push({ date: entry.date, value: entry.values.CEA, left: dateToPercent(entry.date) })
    }
    if (entry.values?.CA_19_9 != null) {
      ca199Points.push({ date: entry.date, value: entry.values.CA_19_9, left: dateToPercent(entry.date) })
    }
  }
  return { cea: ceaPoints, ca199: ca199Points }
})

// ── Track definitions ──────────────────────────────────
const showAllTracks = ref(false)

interface TrackDef {
  key: string
  label: string
  icon: string
  color: string
  bgColor: string
  borderColor: string
}

const trackDefs: TrackDef[] = [
  { key: 'chemo', label: 'treatmentMap.tracks.chemo', icon: '💊', color: 'text-blue-700', bgColor: 'bg-blue-500', borderColor: 'border-blue-300' },
  { key: 'immuno', label: 'treatmentMap.tracks.immuno', icon: '🛡️', color: 'text-violet-700', bgColor: 'bg-violet-500', borderColor: 'border-violet-300' },
  { key: 'bio', label: 'treatmentMap.tracks.bio', icon: '🧬', color: 'text-emerald-700', bgColor: 'bg-emerald-500', borderColor: 'border-emerald-300' },
  { key: 'support', label: 'treatmentMap.tracks.support', icon: '💉', color: 'text-amber-700', bgColor: 'bg-amber-500', borderColor: 'border-amber-300' },
  { key: 'events', label: 'treatmentMap.tracks.events', icon: '📋', color: 'text-gray-700', bgColor: 'bg-gray-500', borderColor: 'border-gray-300' },
  { key: 'markers', label: 'treatmentMap.tracks.markers', icon: '📈', color: 'text-rose-700', bgColor: 'bg-rose-500', borderColor: 'border-rose-300' },
]

function trackHasData(key: string): boolean {
  switch (key) {
    case 'chemo': return chemoEvents.value.length > 0
    case 'support': return supportEvents.value.length > 0
    case 'events': return clinicalEvents.value.length > 0
    case 'markers': return !!markerData.value?.cea.length || !!markerData.value?.ca199.length
    case 'immuno': return false // future
    case 'bio': return false // future
    default: return false
  }
}

const visibleTracks = computed(() =>
  showAllTracks.value ? trackDefs : trackDefs.filter(t => trackHasData(t.key)),
)

// ── Event icons ────────────────────────────────────────
function eventIcon(type: string): string {
  switch (type) {
    case 'surgery': return '🔪'
    case 'scan':
    case 'imaging': return '📡'
    case 'consultation': return '🩺'
    default: return '📅'
  }
}

// ── Marker sparkline helpers ───────────────────────────
function sparklinePath(points: Array<{ left: number; value: number }>, maxVal: number): string {
  if (points.length < 2) return ''
  const h = 32 // track inner height
  return points.map((p, i) => {
    const x = p.left
    const y = 100 - (p.value / maxVal) * 100
    const yPx = (y / 100) * h
    return `${i === 0 ? 'M' : 'L'} ${x}% ${yPx}`
  }).join(' ')
}
</script>

<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('treatmentMap.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('treatmentMap.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <UBadge v-if="protocol?.current_cycle" variant="subtle" color="info" size="xs">
          {{ $t('timeline.currentCycle', { n: protocol.current_cycle }) }}
        </UBadge>
        <UButton
          :variant="showAllTracks ? 'solid' : 'ghost'"
          size="xs"
          color="neutral"
          @click="showAllTracks = !showAllTracks"
        >
          {{ $t('treatmentMap.showAll') }}
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="timeline?.error || timelineError?.message" />
    <SkeletonLoader v-if="!timeline && timelineStatus === 'pending'" variant="card" />

    <!-- Treatment Map -->
    <div v-else-if="months.length" class="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <!-- Scrollable container -->
      <div class="overflow-x-auto" style="-webkit-overflow-scrolling: touch">
        <div class="min-w-[700px]">
          <!-- Month header row -->
          <div class="flex border-b border-gray-100 sticky top-0 bg-white z-10">
            <div class="w-28 shrink-0 px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider border-r border-gray-100 sticky left-0 bg-white z-20">
              {{ $t('treatmentMap.track') }}
            </div>
            <div class="flex-1 relative">
              <div class="flex">
                <div
                  v-for="month in months"
                  :key="month.label"
                  class="flex-1 px-2 py-2 text-[10px] font-medium text-gray-400 text-center border-r border-gray-50 last:border-r-0"
                >
                  {{ month.shortLabel }}
                </div>
              </div>
            </div>
          </div>

          <!-- Track rows -->
          <template v-for="track in visibleTracks" :key="track.key">
            <div class="flex border-b border-gray-50 last:border-b-0 group hover:bg-gray-50/50 transition-colors">
              <!-- Track label (sticky left) -->
              <div class="w-28 shrink-0 px-3 py-3 flex items-center gap-1.5 border-r border-gray-100 sticky left-0 bg-white group-hover:bg-gray-50/50 z-10 transition-colors">
                <span class="text-sm">{{ track.icon }}</span>
                <span class="text-xs font-medium truncate" :class="track.color">{{ $t(track.label) }}</span>
              </div>

              <!-- Track content area -->
              <div class="flex-1 relative h-10 overflow-hidden">
                <!-- Month grid lines -->
                <div class="absolute inset-0 flex pointer-events-none">
                  <div v-for="month in months" :key="'grid-' + month.label" class="flex-1 border-r border-gray-50 last:border-r-0" />
                </div>

                <!-- Chemo track: cycle blocks -->
                <template v-if="track.key === 'chemo'">
                  <div
                    v-for="ev in chemoEvents"
                    :key="ev.id"
                    class="absolute top-1 h-8 rounded cursor-pointer hover:ring-2 hover:ring-blue-400/50 transition-all flex items-center justify-center"
                    :class="`${track.bgColor}/20 border ${track.borderColor}`"
                    :style="{ left: `${ev.left}%`, width: `${ev.width}%`, minWidth: '28px' }"
                    :title="`${ev.title} — ${formatDate(ev.date)}`"
                    @click="drilldown.open({ type: 'treatment_event', id: ev.id, label: ev.title })"
                  >
                    <span class="text-[9px] font-bold text-blue-700 truncate px-1">{{ ev.title.match(/C\d+/)?.[0] || ev.title.slice(0, 4) }}</span>
                  </div>
                </template>

                <!-- Immuno track: future placeholder -->
                <template v-else-if="track.key === 'immuno'">
                  <div v-if="!trackHasData('immuno')" class="absolute inset-0 flex items-center justify-center">
                    <span class="text-[10px] text-gray-300 italic">{{ $t('treatmentMap.noData') }}</span>
                  </div>
                </template>

                <!-- Bio track: future placeholder -->
                <template v-else-if="track.key === 'bio'">
                  <div v-if="!trackHasData('bio')" class="absolute inset-0 flex items-center justify-center">
                    <span class="text-[10px] text-gray-300 italic">{{ $t('treatmentMap.noData') }}</span>
                  </div>
                </template>

                <!-- Support track: continuous bar + event dots -->
                <template v-else-if="track.key === 'support'">
                  <!-- Clexane continuous bar (spans full timeline if active) -->
                  <div class="absolute top-3 left-0 right-0 h-1 bg-amber-200 rounded-full" />
                  <div
                    v-for="ev in supportEvents"
                    :key="ev.id"
                    class="absolute top-1.5 w-2.5 h-2.5 rounded-full bg-amber-500 border border-white cursor-pointer hover:scale-150 transition-transform"
                    :style="{ left: `${ev.left}%` }"
                    :title="`${ev.title} — ${formatDate(ev.date)}`"
                    @click="drilldown.open({ type: 'treatment_event', id: ev.id, label: ev.title })"
                  />
                </template>

                <!-- Events track: markers -->
                <template v-else-if="track.key === 'events'">
                  <div
                    v-for="ev in clinicalEvents"
                    :key="ev.id"
                    class="absolute top-1 h-8 flex items-center cursor-pointer hover:scale-110 transition-transform"
                    :style="{ left: `${ev.left}%` }"
                    :title="`${ev.title} — ${formatDate(ev.date)}`"
                    @click="drilldown.open({ type: 'treatment_event', id: ev.id, label: ev.title })"
                  >
                    <span class="text-sm">{{ eventIcon(ev.type) }}</span>
                  </div>
                </template>

                <!-- Markers track: sparkline overlay -->
                <template v-else-if="track.key === 'markers'">
                  <svg v-if="markerData" class="absolute inset-0 w-full h-full overflow-visible" preserveAspectRatio="none">
                    <!-- CEA line -->
                    <path
                      v-if="markerData.cea.length >= 2"
                      :d="sparklinePath(markerData.cea, Math.max(...markerData.cea.map(p => p.value)) * 1.2)"
                      fill="none"
                      stroke="#f43f5e"
                      stroke-width="1.5"
                      vector-effect="non-scaling-stroke"
                    />
                    <!-- CA19-9 line -->
                    <path
                      v-if="markerData.ca199.length >= 2"
                      :d="sparklinePath(markerData.ca199, Math.max(...markerData.ca199.map(p => p.value)) * 1.2)"
                      fill="none"
                      stroke="#8b5cf6"
                      stroke-width="1.5"
                      stroke-dasharray="3,2"
                      vector-effect="non-scaling-stroke"
                    />
                    <!-- Data point dots -->
                    <circle
                      v-for="(p, i) in markerData.cea"
                      :key="'cea-' + i"
                      :cx="`${p.left}%`"
                      :cy="32 - (p.value / (Math.max(...markerData.cea.map(pp => pp.value)) * 1.2)) * 32"
                      r="2.5"
                      fill="#f43f5e"
                      class="cursor-pointer"
                    >
                      <title>CEA: {{ p.value.toLocaleString() }} ({{ formatDate(p.date) }})</title>
                    </circle>
                    <circle
                      v-for="(p, i) in markerData.ca199"
                      :key="'ca199-' + i"
                      :cx="`${p.left}%`"
                      :cy="32 - (p.value / (Math.max(...markerData.ca199.map(pp => pp.value)) * 1.2)) * 32"
                      r="2.5"
                      fill="#8b5cf6"
                      class="cursor-pointer"
                    >
                      <title>CA19-9: {{ p.value.toLocaleString() }} ({{ formatDate(p.date) }})</title>
                    </circle>
                  </svg>
                  <!-- Legend -->
                  <div class="absolute top-0 right-2 flex items-center gap-2 text-[8px]">
                    <span class="flex items-center gap-0.5"><span class="w-2 h-0.5 bg-rose-500 inline-block" /> CEA</span>
                    <span class="flex items-center gap-0.5"><span class="w-2 h-0.5 bg-violet-500 inline-block border-t border-dashed" /> CA19-9</span>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Today marker info -->
      <div class="px-4 py-2 border-t border-gray-100 text-[10px] text-gray-400 flex items-center justify-between">
        <span>{{ $t('treatmentMap.treatmentLine', { n: 1 }) }} &mdash; mFOLFOX6 90%</span>
        <span>{{ $t('treatmentMap.totalEvents', { count: timeline?.total ?? 0 }) }}</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="timelineStatus !== 'pending' && !timelineError" class="text-center py-16">
      <UIcon name="i-lucide-gantt-chart" class="w-10 h-10 text-gray-300 mx-auto mb-3" />
      <p class="text-sm text-gray-500">{{ $t('treatmentMap.noData') }}</p>
    </div>
  </div>
</template>
