<script setup lang="ts">
/**
 * Append-only timeline of funnel state changes for one card (#395).
 * Pulls from /api/funnel/audit/{card_id} — every entry is immutable, tied
 * to an actor (physician / advocate / agent) and includes the rationale.
 */
interface FunnelAuditEvent {
  event_id?: string
  card_id: string
  patient_id: string
  nct_id: string
  actor_type: 'human' | 'agent' | 'system'
  actor_id: string
  actor_display_name?: string
  event_type: string
  from_stage?: string | null
  to_stage?: string | null
  rationale?: string
  metadata?: Record<string, unknown>
  created_at: string
}

const props = defineProps<{ cardId: string; compact?: boolean }>()

const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

const { data, status, error, refresh } = fetchApi<{
  events: FunnelAuditEvent[]
  count: number
  card_id: string
}>(`/funnel/audit/${encodeURIComponent(props.cardId)}`, { lazy: true, server: false })

defineExpose({ refresh })

const actorStyles: Record<string, { color: string; icon: string; label: string }> = {
  human: { color: 'text-emerald-700 bg-emerald-50 border-emerald-200', icon: 'i-lucide-user', label: 'Human' },
  agent: { color: 'text-indigo-700 bg-indigo-50 border-indigo-200', icon: 'i-lucide-bot', label: 'Agent' },
  system: { color: 'text-gray-700 bg-gray-50 border-gray-200', icon: 'i-lucide-cog', label: 'System' },
}

function eventLabel(ev: FunnelAuditEvent): string {
  const t = ev.event_type.replace(/_/g, ' ')
  if (ev.from_stage && ev.to_stage) return `${t}: ${ev.from_stage} → ${ev.to_stage}`
  if (ev.to_stage) return `${t} → ${ev.to_stage}`
  return t
}
</script>

<template>
  <div class="text-xs">
    <div v-if="status === 'pending'" class="text-gray-400 italic">Loading audit trail…</div>
    <div v-else-if="error || data?.count === undefined" class="text-red-500">
      Audit log unavailable
    </div>
    <div v-else-if="data && data.count === 0" class="text-gray-400 italic">No events yet.</div>
    <ol v-else class="space-y-1.5">
      <li
        v-for="ev in data?.events ?? []"
        :key="ev.event_id || `${ev.card_id}-${ev.created_at}-${ev.event_type}`"
        class="rounded-md border px-2 py-1.5"
        :class="actorStyles[ev.actor_type]?.color || actorStyles.system.color"
      >
        <div class="flex items-center gap-1.5">
          <UIcon :name="actorStyles[ev.actor_type]?.icon || actorStyles.system.icon" class="w-3 h-3" />
          <span class="font-medium">{{ ev.actor_display_name || ev.actor_id }}</span>
          <span class="text-gray-500">·</span>
          <span class="font-mono">{{ eventLabel(ev) }}</span>
          <span class="ml-auto text-gray-400">{{ formatDate(ev.created_at) }}</span>
        </div>
        <p v-if="ev.rationale && !props.compact" class="text-gray-700 mt-0.5 pl-4.5">
          {{ ev.rationale }}
        </p>
      </li>
    </ol>
  </div>
</template>
