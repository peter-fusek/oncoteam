<script setup lang="ts">
/**
 * Patient-wide audit trail (#399 S1).
 *
 * Merges two append-only event streams:
 *  - /api/funnel/audit/patient — every clinical-funnel state change (#395)
 *  - /api/oncopanel/audit      — physician approve/dismiss of NGS panels
 *
 * Events are normalized to a common shape and sorted newest-first. This
 * is the "compliance view" surface — every action, every actor, every
 * rationale. No UI to mutate; read-only timeline.
 */
interface FunnelEvent {
  event_id?: string
  card_id: string
  nct_id: string
  actor_type: 'human' | 'agent' | 'system'
  actor_id: string
  actor_display_name?: string
  event_type: string
  from_stage?: string | null
  to_stage?: string | null
  rationale?: string
  created_at: string
}
interface OncopanelEvent {
  event_id?: string
  ts: string
  actor_type: string
  actor_id: string
  actor_display_name?: string
  action: string
  document_id?: number | string
  panel_id?: string
  rationale?: string
  variant_count?: number
}

const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const funnelData = fetchApi<{
  events: FunnelEvent[]
  count: number
  patient_id: string
}>('/funnel/audit/patient?limit=400', { lazy: true, server: false })

const oncopanelData = fetchApi<{
  events: OncopanelEvent[]
  count: number
}>('/oncopanel/audit', { lazy: true, server: false })

interface NormalizedEvent {
  id: string
  ts: string
  actor_type: string
  actor_display: string
  surface: 'funnel' | 'oncopanel'
  label: string
  rationale: string
  link?: string
}

const actorFilter = ref<'all' | 'human' | 'agent' | 'system'>('all')
const surfaceFilter = ref<'all' | 'funnel' | 'oncopanel'>('all')

const merged = computed<NormalizedEvent[]>(() => {
  const out: NormalizedEvent[] = []
  for (const ev of funnelData.data.value?.events ?? []) {
    const label = ev.from_stage && ev.to_stage
      ? `${ev.event_type}: ${ev.from_stage} → ${ev.to_stage}`
      : ev.to_stage
        ? `${ev.event_type} → ${ev.to_stage}`
        : ev.event_type
    out.push({
      id: ev.event_id || `${ev.card_id}-${ev.created_at}-${ev.event_type}`,
      ts: ev.created_at,
      actor_type: ev.actor_type,
      actor_display: ev.actor_display_name || ev.actor_id,
      surface: 'funnel',
      label: `${label} · ${ev.nct_id}`,
      rationale: ev.rationale || '',
    })
  }
  for (const ev of oncopanelData.data.value?.events ?? []) {
    out.push({
      id: ev.event_id || `oncopanel-${ev.ts}-${ev.action}`,
      ts: ev.ts,
      actor_type: ev.actor_type,
      actor_display: ev.actor_display_name || ev.actor_id,
      surface: 'oncopanel',
      label: `oncopanel ${ev.action}${ev.panel_id ? ` · ${ev.panel_id}` : ''}${ev.variant_count !== undefined ? ` · ${ev.variant_count} variants` : ''}`,
      rationale: ev.rationale || '',
    })
  }
  return out
    .filter(e => actorFilter.value === 'all' || e.actor_type === actorFilter.value)
    .filter(e => surfaceFilter.value === 'all' || e.surface === surfaceFilter.value)
    .sort((a, b) => b.ts.localeCompare(a.ts))
})

const actorStyles: Record<string, string> = {
  human: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  agent: 'text-indigo-700 bg-indigo-50 border-indigo-200',
  system: 'text-gray-700 bg-gray-50 border-gray-200',
}

const surfaceIcon: Record<string, string> = {
  funnel: 'i-lucide-kanban',
  oncopanel: 'i-lucide-microscope',
}

const loading = computed(
  () => funnelData.status.value === 'pending' || oncopanelData.status.value === 'pending',
)
const errored = computed(
  () => Boolean(funnelData.error.value || oncopanelData.error.value),
)
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="text-sm font-semibold text-gray-900">Patient audit trail</h2>
      <p class="text-xs text-gray-500">
        Immutable append-only timeline — every clinical decision by physician, advocate, or agent.
      </p>
      <UButton
        icon="i-lucide-refresh-cw"
        variant="ghost"
        size="xs"
        color="neutral"
        class="ml-auto"
        @click="() => { funnelData.refresh(); oncopanelData.refresh() }"
      />
    </div>

    <div class="flex gap-2 flex-wrap text-xs">
      <UButtonGroup>
        <UButton
          v-for="f in (['all', 'human', 'agent', 'system'] as const)"
          :key="f"
          :variant="actorFilter === f ? 'solid' : 'soft'"
          size="xs"
          color="neutral"
          @click="actorFilter = f"
        >
          {{ f }}
        </UButton>
      </UButtonGroup>
      <UButtonGroup>
        <UButton
          v-for="f in (['all', 'funnel', 'oncopanel'] as const)"
          :key="f"
          :variant="surfaceFilter === f ? 'solid' : 'soft'"
          size="xs"
          color="neutral"
          @click="surfaceFilter = f"
        >
          {{ f }}
        </UButton>
      </UButtonGroup>
      <span class="ml-auto text-xs text-gray-400">
        {{ merged.length }} events
      </span>
    </div>

    <SkeletonLoader v-if="loading && !merged.length" variant="list" />
    <div v-else-if="errored && !merged.length" class="text-xs text-red-600">
      Audit log unavailable right now.
    </div>
    <EmptyState
      v-else-if="!merged.length"
      icon="i-lucide-file-clock"
      message="No audit events yet."
    />

    <ol v-else class="space-y-1.5">
      <li
        v-for="ev in merged"
        :key="ev.id"
        class="rounded-md border px-2 py-1.5 text-xs"
        :class="actorStyles[ev.actor_type] || actorStyles.system"
      >
        <div class="flex items-center gap-1.5">
          <UIcon :name="surfaceIcon[ev.surface]" class="w-3 h-3" />
          <span class="font-medium">{{ ev.actor_display }}</span>
          <span class="text-gray-500">·</span>
          <span class="font-mono">{{ ev.label }}</span>
          <span class="ml-auto text-gray-400">{{ formatDate(ev.ts) }}</span>
        </div>
        <p v-if="ev.rationale" class="text-gray-700 mt-0.5 pl-4.5">
          {{ ev.rationale }}
        </p>
      </li>
    </ol>
  </div>
</template>
