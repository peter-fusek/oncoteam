<script setup lang="ts">
/**
 * Pending oncopanel extraction awaiting physician triage (#399 S1).
 *
 * The document pipeline stores each extracted NGS report under
 * `pending_oncopanel:{patient_id}:{document_id}` in oncofiles agent_state.
 * Physician reviews the parsed variants here and either:
 *  - Approves → variants merge into PatientProfile.oncopanel_history.
 *  - Dismisses → pending flips to dismissed; no patient-state change.
 *
 * Every action is audited via /api/oncopanel/audit.
 */
interface VariantPreview {
  gene: string
  protein_short: string
  tier: string
  significance: string
  vaf: number | null
}

interface PendingSummary {
  panel_id: string
  report_date: string
  lab: string
  methodology: string
  sample_type: string
  msi_status: string
  mmr_status: string
  tmb_score: number | null
  tmb_category: string
  variant_count: number
  cnv_count: number
  variants_preview: VariantPreview[]
}

export interface PendingItem {
  key: string
  document_id: number | string
  timestamp: string
  status: string
  extraction_cost_usd: number
  extraction_model: string
  summary: PendingSummary | null
  parse_error: boolean
  rationale: string
}

const props = defineProps<{ item: PendingItem }>()
const emit = defineEmits<{
  (e: 'triaged', payload: { document_id: number | string; action: 'approve' | 'dismiss' }): void
}>()

const { postApi } = useOncoteamApi()
const { activeRole } = useUserRole()
const { formatDate } = useFormatDate()

const canTriage = computed(() => activeRole.value === 'doctor' || activeRole.value === 'advocate')

const approveOpen = ref(false)
const dismissOpen = ref(false)
const rationale = ref('')
const busy = ref(false)
const submitError = ref<string | null>(null)

function openApprove() {
  rationale.value = ''
  submitError.value = null
  approveOpen.value = true
}

function openDismiss() {
  rationale.value = ''
  submitError.value = null
  dismissOpen.value = true
}

async function submit(action: 'approve' | 'dismiss') {
  const r = rationale.value.trim()
  if (!r) {
    submitError.value = 'Rationale is required.'
    return
  }
  busy.value = true
  submitError.value = null
  try {
    await postApi('/oncopanel/pending', {
      action,
      document_id: props.item.document_id,
      rationale: r,
    })
    emit('triaged', { document_id: props.item.document_id, action })
    approveOpen.value = false
    dismissOpen.value = false
  }
  catch (err: unknown) {
    submitError.value = err instanceof Error ? err.message : `${action} failed`
  }
  finally {
    busy.value = false
  }
}

const tierColor: Record<string, 'error' | 'warning' | 'info' | 'neutral'> = {
  IA: 'error',
  IB: 'error',
  IIC: 'warning',
  IID: 'warning',
  III: 'info',
}
</script>

<template>
  <div class="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 space-y-3">
    <div class="flex items-start gap-2">
      <UIcon name="i-lucide-microscope" class="w-5 h-5 text-emerald-700 mt-0.5 shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-semibold text-gray-900">
            Oncopanel · doc #{{ item.document_id }}
          </span>
          <UBadge v-if="item.summary?.sample_type" variant="subtle" size="xs" color="neutral">
            {{ item.summary.sample_type }}
          </UBadge>
          <UBadge v-if="item.summary?.methodology" variant="subtle" size="xs" color="neutral">
            {{ item.summary.methodology }}
          </UBadge>
          <UBadge v-if="item.summary?.report_date" variant="subtle" size="xs" color="success">
            {{ item.summary.report_date }}
          </UBadge>
          <span class="ml-auto text-xs text-gray-400">
            extracted {{ formatDate(item.timestamp) }}
          </span>
        </div>
        <p v-if="item.summary?.lab" class="text-xs text-gray-500 mt-0.5">
          {{ item.summary.lab }}
        </p>
      </div>
    </div>

    <!-- Panel summary grid -->
    <div v-if="item.summary" class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
      <div class="rounded-md border border-emerald-100 bg-white px-2 py-1.5">
        <div class="text-[10px] uppercase tracking-wide text-gray-400">Variants</div>
        <div class="font-semibold text-gray-900">{{ item.summary.variant_count }}</div>
      </div>
      <div class="rounded-md border border-emerald-100 bg-white px-2 py-1.5">
        <div class="text-[10px] uppercase tracking-wide text-gray-400">CNVs</div>
        <div class="font-semibold text-gray-900">{{ item.summary.cnv_count }}</div>
      </div>
      <div class="rounded-md border border-emerald-100 bg-white px-2 py-1.5">
        <div class="text-[10px] uppercase tracking-wide text-gray-400">MSI · MMR</div>
        <div class="font-semibold text-gray-900">
          {{ item.summary.msi_status || '—' }} · {{ item.summary.mmr_status || '—' }}
        </div>
      </div>
      <div class="rounded-md border border-emerald-100 bg-white px-2 py-1.5">
        <div class="text-[10px] uppercase tracking-wide text-gray-400">TMB</div>
        <div class="font-semibold text-gray-900">
          <span v-if="item.summary.tmb_score !== null">
            {{ item.summary.tmb_score }} ·
          </span>
          {{ item.summary.tmb_category || '—' }}
        </div>
      </div>
    </div>

    <!-- Variant preview -->
    <div v-if="item.summary?.variants_preview?.length" class="space-y-1">
      <div
        v-for="v in item.summary.variants_preview"
        :key="`${v.gene}-${v.protein_short}`"
        class="flex items-center gap-2 text-xs bg-white rounded-md border border-emerald-100 px-2 py-1"
      >
        <span class="font-semibold text-gray-900 w-14">{{ v.gene }}</span>
        <span class="font-mono text-gray-700 flex-1 truncate">{{ v.protein_short || '—' }}</span>
        <UBadge v-if="v.tier" variant="subtle" size="xs" :color="tierColor[v.tier] || 'neutral'">
          {{ v.tier }}
        </UBadge>
        <UBadge v-if="v.significance" variant="subtle" size="xs" color="neutral">
          {{ v.significance }}
        </UBadge>
        <span v-if="v.vaf !== null" class="text-gray-500 text-[11px] tabular-nums w-12 text-right">
          {{ Math.round((v.vaf as number) * 10000) / 100 }}%
        </span>
      </div>
    </div>

    <div v-if="item.parse_error" class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5">
      Unable to parse a structured panel from the extraction response. Dismiss + re-extract, or edit panel manually via API.
    </div>

    <div v-if="!item.summary && !item.parse_error" class="text-xs text-gray-400 italic">
      No summary available.
    </div>

    <div class="flex items-center gap-2 text-xs text-gray-500">
      <span v-if="item.extraction_model">model: <span class="font-mono">{{ item.extraction_model }}</span></span>
      <span v-if="item.extraction_cost_usd">· ${{ item.extraction_cost_usd.toFixed(4) }}</span>
    </div>

    <div v-if="canTriage" class="flex items-center gap-2 pt-1 border-t border-emerald-100">
      <UButton
        :disabled="item.parse_error"
        size="xs"
        color="success"
        variant="solid"
        icon="i-lucide-check"
        @click="openApprove"
      >
        Approve + merge
      </UButton>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        icon="i-lucide-x"
        @click="openDismiss"
      >
        Dismiss
      </UButton>
    </div>

    <!-- Approve dialog -->
    <UModal v-model:open="approveOpen">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-check-circle-2" class="w-4 h-4 text-emerald-600" />
              <span class="text-sm font-semibold text-gray-900">
                Approve oncopanel &rarr; merge into patient profile
              </span>
            </div>
          </template>
          <div class="space-y-3 text-xs">
            <p class="text-gray-500">
              This will merge {{ item.summary?.variant_count ?? 0 }} variants
              + {{ item.summary?.cnv_count ?? 0 }} CNVs into q1b's oncopanel history.
              Eligibility rules + dashboard surfaces pick up the change immediately.
              The approval is audit-logged and not reversible via silent overwrite.
            </p>
            <div>
              <label class="block font-medium text-gray-700 mb-1">Rationale (required)</label>
              <UTextarea
                v-model="rationale"
                :rows="3"
                placeholder="e.g. Matches Feb NGS. G12S + ATM biallelic + TP53 splice verified against source doc."
              />
            </div>
            <div v-if="submitError" class="text-red-600">{{ submitError }}</div>
          </div>
          <template #footer>
            <div class="flex items-center gap-2 justify-end">
              <UButton size="sm" variant="ghost" color="neutral" @click="approveOpen = false">
                Cancel
              </UButton>
              <UButton
                size="sm"
                color="success"
                :loading="busy"
                :disabled="!rationale.trim()"
                @click="submit('approve')"
              >
                Approve + merge
              </UButton>
            </div>
          </template>
        </UCard>
      </template>
    </UModal>

    <!-- Dismiss dialog -->
    <UModal v-model:open="dismissOpen">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-archive" class="w-4 h-4 text-gray-500" />
              <span class="text-sm font-semibold text-gray-900">
                Dismiss oncopanel extraction
              </span>
            </div>
          </template>
          <div class="space-y-3 text-xs">
            <p class="text-gray-500">
              The pending entry stays visible (append-only audit) but will not merge
              into the patient's oncopanel history. Re-extraction requires a new
              document_pipeline run.
            </p>
            <div>
              <label class="block font-medium text-gray-700 mb-1">Reason (required)</label>
              <UTextarea
                v-model="rationale"
                :rows="3"
                placeholder="e.g. Wrong patient; OCR corruption; superseded by later panel."
              />
            </div>
            <div v-if="submitError" class="text-red-600">{{ submitError }}</div>
          </div>
          <template #footer>
            <div class="flex items-center gap-2 justify-end">
              <UButton size="sm" variant="ghost" color="neutral" @click="dismissOpen = false">
                Cancel
              </UButton>
              <UButton
                size="sm"
                color="neutral"
                :loading="busy"
                :disabled="!rationale.trim()"
                @click="submit('dismiss')"
              >
                Dismiss
              </UButton>
            </div>
          </template>
        </UCard>
      </template>
    </UModal>
  </div>
</template>
