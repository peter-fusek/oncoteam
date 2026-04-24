<script setup lang="ts">
/**
 * Admin-only banner — surfaces Gate-1-only patients waiting for manual
 * oncoteam onboarding (#422).
 *
 * Source: GET /api/internal/onboarding-queue (populated by the daily
 * `patient_registry_sync` agent). A Gate-1-only patient exists in
 * oncofiles but has no PatientProfile in oncoteam — the two-gate
 * visibility rule keeps them out of the clinical dropdown until an
 * admin explicitly completes Gate 2.
 *
 * Dismissal is stored per-user in agent_state (cross-device) — TODO
 * next sprint when the full /admin/onboarding page + dismissal endpoint
 * land. For now the banner always renders when the queue is non-empty
 * so the signal is not silently lost.
 */
interface QueueItem {
  slug: string
  name: string
  patient_type: string
  documents: number
  first_seen_in_oncofiles: string
  flagged_at: string
}

const { activeRole } = useUserRole()

// The queue endpoint lives on the admin/internal path, not the regular
// oncoteam /api/* namespace, so we fetch directly through the proxy.
const { data, status, error, refresh } = useFetch<{
  queue: QueueItem[]
  count: number
  stale: boolean
  snapshot_timestamp: string | null
  error?: string
}>('/api/oncoteam/internal/onboarding-queue', {
  lazy: true,
  server: false,
  // Poll every 2 min so a freshly-fired sync agent surfaces without
  // requiring a full page reload.
  key: 'onboarding-queue',
})

const { formatDate } = useFormatDate()

const isAdmin = computed(() => activeRole.value === 'advocate' || activeRole.value === 'doctor')
const visible = computed(
  () => isAdmin.value && !error.value && !data.value?.error && (data.value?.count ?? 0) > 0,
)
</script>

<template>
  <div
    v-if="visible"
    class="mb-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-xs"
  >
    <div class="flex items-start gap-2">
      <UIcon name="i-lucide-user-plus" class="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-semibold text-amber-900">
            {{ data?.count }} pacient{{ (data?.count || 0) === 1 ? '' : 'i' }} čaká na oncoteam onboarding
          </span>
          <span class="text-amber-700">—</span>
          <span class="text-gray-600">
            existujú v oncofiles, ale nemajú klinický profil. Priradiť profil + rolu.
          </span>
          <NuxtLink
            to="/admin/onboarding"
            class="ml-auto text-amber-900 font-semibold underline decoration-dotted hover:decoration-solid"
          >
            Open onboarding →
          </NuxtLink>
          <UButton
            icon="i-lucide-refresh-cw"
            variant="ghost"
            size="xs"
            color="neutral"
            :disabled="status === 'pending'"
            @click="refresh"
          />
        </div>
        <ul class="mt-2 space-y-0.5 pl-2">
          <li
            v-for="item in data?.queue"
            :key="item.slug"
            class="flex items-center gap-2 text-gray-700"
          >
            <span class="font-mono text-[11px] text-gray-500 w-28 shrink-0">{{ item.slug }}</span>
            <span class="font-medium">{{ item.name || '—' }}</span>
            <UBadge
              v-if="item.patient_type"
              variant="subtle"
              size="xs"
              :color="item.patient_type === 'oncology' ? 'warning' : 'info'"
            >
              {{ item.patient_type }}
            </UBadge>
            <span class="text-gray-500 text-[11px]">{{ item.documents }} dok.</span>
            <span v-if="item.flagged_at" class="ml-auto text-gray-400 text-[11px]">
              detected {{ formatDate(item.flagged_at) }}
            </span>
          </li>
        </ul>
        <p class="mt-2 text-[11px] text-amber-700/80">
          Onboarding agent: detection-only — nikdy auto-registruje (#422 dvojgate pravidlo).
          Kompletný /admin/onboarding formulár shippuje ďalší sprint.
        </p>
      </div>
    </div>
  </div>
</template>
