<script setup lang="ts">
/**
 * /admin/onboarding — complete Gate 2 for Gate-1-only patients (#422 Part E).
 *
 * Data flow:
 *   GET  /api/internal/onboarding-queue     — pending Gate-1-only patients
 *                                             (populated by patient_registry_sync agent)
 *   POST /api/internal/onboard-patient      — with register_locally_only=true,
 *                                             skips oncofiles creation (patient
 *                                             already exists there) and just
 *                                             writes to oncoteam's _patient_registry
 *   POST /api/internal/access-rights        — updates the current user's
 *                                             patient_roles[pid] = selected role
 *
 * After both succeed, the patient disappears from the queue and appears
 * in the dashboard patient switcher (writable or 🔒 admin-readonly group
 * depending on the role assigned).
 *
 * Access: admin-only surface. No clinical interpretation rendered here —
 * just the onboarding form. Pending patient has zero clinical context
 * until the advocate fills in diagnosis / treatment fields.
 */
import type { UserConfig } from '~/server/utils/access-rights'

interface QueueItem {
  slug: string
  name: string
  patient_type: string
  documents: number
  first_seen_in_oncofiles: string
  flagged_at: string
}

definePageMeta({
  title: 'Onboarding queue',
})

const { user } = useUserSession()
const { activeRole } = useUserRole()
const { formatDate } = useFormatDate()

const isAdmin = computed(() => activeRole.value === 'advocate' || activeRole.value === 'doctor')

const queueData = useFetch<{
  queue: QueueItem[]
  count: number
  stale: boolean
  snapshot_timestamp: string | null
  error?: string
}>('/api/oncoteam/internal/onboarding-queue', {
  lazy: true,
  server: false,
  key: 'admin-onboarding-queue',
})

// Onboarding form state (one at a time).
const selected = ref<QueueItem | null>(null)
const busy = ref(false)
const formError = ref<string | null>(null)
const formSuccess = ref<string | null>(null)

const form = reactive({
  diagnosisCode: '',
  diagnosisDescription: '',
  treatmentRegimen: '',
  notificationPolicy: 'silent' as 'silent' | 'admin' | 'patient+admin',
  role: 'admin-readonly' as 'admin-readonly' | 'family-readonly' | 'advocate' | 'doctor',
})

function openForm(item: QueueItem) {
  selected.value = item
  formError.value = null
  formSuccess.value = null
  form.diagnosisCode = ''
  form.diagnosisDescription = ''
  form.treatmentRegimen = ''
  form.notificationPolicy = 'silent'
  form.role = 'admin-readonly'
}

function closeForm() {
  selected.value = null
}

async function submitOnboarding() {
  if (!selected.value) return
  busy.value = true
  formError.value = null
  formSuccess.value = null

  try {
    // Step 1: register the patient in oncoteam's local registry.
    await $fetch('/api/oncoteam/internal/onboard-patient', {
      method: 'POST',
      body: {
        patient_id: selected.value.slug,
        display_name: selected.value.name || selected.value.slug,
        diagnosis_code: form.diagnosisCode.trim(),
        diagnosis_summary: form.diagnosisDescription.trim(),
        treatment_regimen: form.treatmentRegimen.trim(),
        notification_policy: form.notificationPolicy,
        register_locally_only: true,
      },
    })

    // Step 2: update the current user's role map entry with a per-patient
    // role assignment for this new slug. Read-modify-write — fetch the
    // current role_map first, then PUT the updated entry back.
    const email = user.value?.email as string
    const rmResp = await $fetch<{ role_map: Record<string, UserConfig> }>(
      '/api/oncoteam/internal/access-rights',
    )
    const rm = rmResp.role_map || {}
    const uc: UserConfig = rm[email] || {
      name: user.value?.name as string | undefined,
      roles: ['advocate'],
      patient_ids: [],
    }
    uc.patient_roles = { ...(uc.patient_roles || {}), [selected.value.slug]: form.role }
    // Also maintain legacy fields for any other consumer that hasn't
    // migrated yet — add the slug to patient_ids if it's not already there.
    const existingIds = new Set(uc.patient_ids || [])
    existingIds.add(selected.value.slug)
    uc.patient_ids = [...existingIds]
    rm[email] = uc
    await $fetch('/api/oncoteam/internal/access-rights', {
      method: 'POST',
      body: { role_map: rm },
    })

    formSuccess.value = `${selected.value.name || selected.value.slug} onboarded — reload to see them in the patient switcher.`
    await queueData.refresh()
    selected.value = null
  }
  catch (err: unknown) {
    formError.value = err instanceof Error ? err.message : 'Onboarding failed'
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-4">
    <div>
      <h1 class="text-2xl font-bold text-gray-900">Onboarding queue</h1>
      <p class="text-sm text-gray-500">
        Patients detected in Oncofiles by the <code class="text-xs">patient_registry_sync</code>
        agent that haven't completed Gate 2 yet (no clinical profile in oncoteam).
        Complete Gate 2 here to make them visible in the patient switcher.
      </p>
    </div>

    <div
      v-if="!isAdmin"
      class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
    >
      This surface is admin-only. Current role: <code>{{ activeRole }}</code>.
    </div>

    <template v-else>
      <SkeletonLoader v-if="queueData.status.value === 'pending' && !queueData.data.value" variant="list" />
      <div
        v-else-if="queueData.error.value || queueData.data.value?.error"
        class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
      >
        Queue snapshot unavailable. The <code class="text-xs">patient_registry_sync</code>
        agent may not have fired yet — it runs daily at 01:45 UTC. Trigger it manually
        via <code class="text-xs">POST /api/internal/trigger-agent {"agent_id": "patient_registry_sync"}</code>
        to seed the snapshot now.
      </div>
      <EmptyState
        v-else-if="!queueData.data.value?.count"
        icon="i-lucide-check-check"
        :message="queueData.data.value?.stale
          ? 'Snapshot pending — agent has not fired yet.'
          : 'Queue empty — every oncofiles patient has a matching clinical profile. ✅'"
      />

      <div v-else class="space-y-3">
        <div class="text-xs text-gray-500">
          {{ queueData.data.value.count }} patient{{ queueData.data.value.count === 1 ? '' : 's' }}
          awaiting Gate 2 · snapshot from
          {{ formatDate(queueData.data.value.snapshot_timestamp) }}
        </div>
        <div
          v-for="item in queueData.data.value.queue"
          :key="item.slug"
          class="rounded-xl border border-gray-200 bg-white p-4 space-y-2"
        >
          <div class="flex items-start gap-3">
            <UIcon name="i-lucide-user-plus" class="w-5 h-5 text-amber-700 mt-0.5 shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-mono text-xs text-gray-500">{{ item.slug }}</span>
                <span class="font-semibold text-gray-900">{{ item.name || '—' }}</span>
                <UBadge
                  v-if="item.patient_type"
                  variant="subtle"
                  size="xs"
                  :color="item.patient_type === 'oncology' ? 'warning' : 'info'"
                >
                  {{ item.patient_type }}
                </UBadge>
                <span class="text-xs text-gray-500">{{ item.documents }} dok.</span>
              </div>
              <p v-if="item.first_seen_in_oncofiles" class="text-xs text-gray-400 mt-0.5">
                In oncofiles since {{ formatDate(item.first_seen_in_oncofiles) }} · flagged {{ formatDate(item.flagged_at) }}
              </p>
            </div>
            <UButton
              size="sm"
              color="primary"
              :disabled="busy && selected?.slug !== item.slug"
              @click="openForm(item)"
            >
              Onboard
            </UButton>
          </div>

          <!-- Inline form for the currently-selected queue item -->
          <div
            v-if="selected?.slug === item.slug"
            class="mt-3 pt-3 border-t border-gray-200 space-y-3"
          >
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <label class="space-y-1">
                <span class="block font-medium text-gray-700">Diagnosis code (ICD-10)</span>
                <input
                  v-model="form.diagnosisCode"
                  class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
                  placeholder="e.g. C50.9, C18.7, Z00.0"
                >
              </label>
              <label class="space-y-1">
                <span class="block font-medium text-gray-700">Treatment regimen</span>
                <input
                  v-model="form.treatmentRegimen"
                  class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
                  placeholder="e.g. AC-T, palliative hormone, (leave empty for preventive)"
                >
              </label>
              <label class="col-span-2 space-y-1">
                <span class="block font-medium text-gray-700">Diagnosis description</span>
                <input
                  v-model="form.diagnosisDescription"
                  class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
                  placeholder="Free-form plain-language summary"
                >
              </label>
              <label class="space-y-1">
                <span class="block font-medium text-gray-700">Notification policy</span>
                <select
                  v-model="form.notificationPolicy"
                  class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
                >
                  <option value="silent">silent — dashboard-only (recommended)</option>
                  <option value="admin">admin — push to admin WhatsApp</option>
                  <option value="patient+admin">patient+admin — push to both</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="block font-medium text-gray-700">Your role for this patient</span>
                <select
                  v-model="form.role"
                  class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
                >
                  <option value="admin-readonly">🔒 admin-readonly — monitor only</option>
                  <option value="family-readonly">🔒 family-readonly — filtered view</option>
                  <option value="advocate">advocate — full write (requires per-patient bearer)</option>
                  <option value="doctor">doctor — physician cockpit access</option>
                </select>
              </label>
            </div>
            <p class="text-[11px] text-gray-500">
              Local-only registration: patient already exists in oncofiles (Gate 1 passed).
              Per-patient bearer token (<code>ONCOFILES_MCP_TOKEN_{{ item.slug.toUpperCase().replace(/-/g, '_') }}</code>)
              is still required on Railway for non-admin-readonly access to work end-to-end.
            </p>

            <div v-if="formError" class="rounded-md bg-red-50 border border-red-200 p-2 text-xs text-red-700">
              {{ formError }}
            </div>
            <div v-if="formSuccess" class="rounded-md bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-700">
              {{ formSuccess }}
            </div>

            <div class="flex items-center gap-2 justify-end">
              <UButton size="sm" variant="ghost" color="neutral" :disabled="busy" @click="closeForm">
                Cancel
              </UButton>
              <UButton
                size="sm"
                color="primary"
                :loading="busy"
                @click="submitOnboarding"
              >
                Complete Gate 2
              </UButton>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
