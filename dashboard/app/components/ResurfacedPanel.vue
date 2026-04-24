<script setup lang="ts">
/**
 * Re-Surfaced panel (#399 S1).
 *
 * A "re_surfaced" event fires when an agent tries to propose an NCT that
 * already exists on the board — the API refuses to create a duplicate
 * card and instead appends a re_surfaced audit event on the existing
 * card. This panel surfaces those events so the physician can re-evaluate
 * a trial that dropped out of view and has been re-discovered by newer
 * agent runs.
 *
 * Grouped by card_id (one row per NCT, with all re-surfacing events
 * attached). Clicking through opens the card's full audit trail.
 */
interface FunnelEvent {
  event_id?: string
  card_id: string
  nct_id: string
  actor_type: string
  actor_id: string
  actor_display_name?: string
  event_type: string
  rationale?: string
  metadata?: { existing_lane?: string; existing_stage?: string; source_agent?: string }
  created_at: string
}

const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const { data, status, error, refresh } = fetchApi<{
  events: FunnelEvent[]
  count: number
  patient_id: string
}>('/funnel/audit/patient?event_type=re_surfaced&limit=200', {
  lazy: true,
  server: false,
})

interface Group {
  nct_id: string
  card_id: string
  last_event: FunnelEvent
  events: FunnelEvent[]
  existing_lane: string
  existing_stage: string
}

const groups = computed<Group[]>(() => {
  const map = new Map<string, Group>()
  for (const ev of data.value?.events ?? []) {
    const key = ev.card_id
    const g = map.get(key)
    if (!g) {
      map.set(key, {
        nct_id: ev.nct_id,
        card_id: ev.card_id,
        last_event: ev,
        events: [ev],
        existing_lane: ev.metadata?.existing_lane || '—',
        existing_stage: ev.metadata?.existing_stage || '—',
      })
    }
    else {
      g.events.push(ev)
      if (ev.created_at > g.last_event.created_at) g.last_event = ev
    }
  }
  return [...map.values()].sort((a, b) =>
    b.last_event.created_at.localeCompare(a.last_event.created_at),
  )
})

const expandedCard = ref<string | null>(null)
function toggle(cardId: string) {
  expandedCard.value = expandedCard.value === cardId ? null : cardId
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="text-sm font-semibold text-gray-900">Re-surfaced trials</h2>
      <p class="text-xs text-gray-500">
        NCTs agents tried to re-propose after a prior decision. Re-evaluate with new data, or confirm the prior dismissal.
      </p>
      <UButton
        icon="i-lucide-refresh-cw"
        variant="ghost"
        size="xs"
        color="neutral"
        class="ml-auto"
        @click="refresh"
      />
    </div>

    <SkeletonLoader v-if="status === 'pending' && !data" variant="cards" />
    <div v-else-if="error" class="text-xs text-red-600">Re-surfaced feed unavailable.</div>
    <EmptyState
      v-else-if="!groups.length"
      icon="i-lucide-rotate-ccw"
      message="No re-surfaced trials. Agents have not tried to re-propose anything yet."
    />

    <div v-else class="space-y-2">
      <div
        v-for="g in groups"
        :key="g.card_id"
        class="rounded-xl border border-amber-200 bg-amber-50/40 p-3"
      >
        <div class="flex items-start gap-2">
          <UIcon name="i-lucide-rotate-ccw" class="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <a
                :href="`https://clinicaltrials.gov/study/${g.nct_id}`"
                target="_blank"
                rel="noopener"
                class="font-mono text-xs text-amber-900 hover:underline"
              >
                {{ g.nct_id }}
              </a>
              <UBadge variant="subtle" size="xs" color="warning">
                re-surfaced {{ g.events.length }}×
              </UBadge>
              <UBadge variant="subtle" size="xs" color="neutral">
                {{ g.existing_lane }} · {{ g.existing_stage }}
              </UBadge>
              <span class="ml-auto text-xs text-gray-400">
                last {{ formatDate(g.last_event.created_at) }}
              </span>
            </div>
            <p v-if="g.last_event.rationale" class="text-xs text-gray-700 mt-1">
              <span class="font-semibold">Last agent rationale:</span> {{ g.last_event.rationale }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 mt-2">
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            :icon="expandedCard === g.card_id ? 'i-lucide-chevron-up' : 'i-lucide-clock'"
            @click="toggle(g.card_id)"
          >
            {{ expandedCard === g.card_id ? 'Hide history' : `Show all ${g.events.length} events` }}
          </UButton>
        </div>

        <div v-if="expandedCard === g.card_id" class="pt-2 border-t border-amber-200 mt-2">
          <FunnelAuditLog :card-id="g.card_id" />
        </div>
      </div>
    </div>
  </div>
</template>
