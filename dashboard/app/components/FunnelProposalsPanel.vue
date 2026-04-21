<script setup lang="ts">
/**
 * Proposals lane (#395). Agent-writable server-backed cards.
 *
 * Physician actions: promote to clinical lane (with rationale), archive, comment.
 * Advocate actions: comment only (promote reserved for physician in Sprint 94).
 * Agent actions: cannot mutate — they POST new proposals via the backend.
 *
 * Every action triggers an append-only audit event on the backend.
 */
interface FunnelCard {
  card_id: string
  patient_id: string
  nct_id: string
  lane: 'proposal' | 'clinical'
  current_stage: string
  title: string
  biomarker_match?: Record<string, string>
  geographic_score?: number | null
  sites_in_scope?: Array<{ facility?: string; city?: string; country?: string; status?: string }>
  ai_suggestions?: Array<Record<string, unknown>>
  source_agent?: string
  source_run_id?: string
  proposal_ttl_expires_at?: string | null
  created_at?: string
}

const { fetchApi, postApi } = useOncoteamApi()
const { activeRole } = useUserRole()
const { formatDate } = useFormatDate()

const { data: proposals, status, error, refresh } = fetchApi<{
  cards: FunnelCard[]
  count: number
  error?: string
}>('/funnel/proposals', { lazy: true, server: false })

// Promote dialog state
const promoteOpen = ref(false)
const promoteCard = ref<FunnelCard | null>(null)
const promoteStage = ref<'Watching' | 'Candidate' | 'Qualified' | 'Contacted' | 'Active'>('Watching')
const promoteRationale = ref('')
const promoteBusy = ref(false)
const promoteError = ref<string | null>(null)

const CLINICAL_STAGES = ['Watching', 'Candidate', 'Qualified', 'Contacted', 'Active'] as const

// Per-card audit toggle
const expandedAudit = ref<Set<string>>(new Set())
function toggleAudit(cardId: string): void {
  const s = new Set(expandedAudit.value)
  if (s.has(cardId)) s.delete(cardId)
  else s.add(cardId)
  expandedAudit.value = s
}

// Derived stats
const activeProposals = computed(() =>
  (proposals.value?.cards ?? []).filter(c => c.current_stage === 'new')
)
const dismissedProposals = computed(() =>
  (proposals.value?.cards ?? []).filter(c => c.current_stage === 'dismissed')
)

function openPromote(card: FunnelCard): void {
  promoteCard.value = card
  promoteStage.value = 'Watching'
  promoteRationale.value = ''
  promoteError.value = null
  promoteOpen.value = true
}

async function submitPromote(): Promise<void> {
  if (!promoteCard.value) return
  const rationale = promoteRationale.value.trim()
  if (!rationale) {
    promoteError.value = 'Rationale is required to promote.'
    return
  }
  promoteBusy.value = true
  promoteError.value = null
  try {
    await postApi('/funnel/cards', {
      action: 'promote',
      card_id: promoteCard.value.card_id,
      to_stage: promoteStage.value,
      rationale,
    })
    promoteOpen.value = false
    promoteCard.value = null
    await refresh()
  }
  catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Promote failed'
    promoteError.value = message
  }
  finally {
    promoteBusy.value = false
  }
}

async function archiveProposal(card: FunnelCard): Promise<void> {
  const rationale = window.prompt('Why dismiss this proposal?')
  if (!rationale?.trim()) return
  try {
    await postApi('/funnel/cards', {
      action: 'archive',
      card_id: card.card_id,
      rationale: rationale.trim(),
    })
    await refresh()
  }
  catch (err) {
    console.error('[funnel] archive failed', err)
  }
}

const canPromote = computed(() => activeRole.value === 'physician' || activeRole.value === 'advocate')
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-baseline gap-3">
      <h2 class="text-sm font-semibold text-gray-900">
        {{ $t('funnel.proposalsTitle', 'Agent proposals') }}
      </h2>
      <p class="text-xs text-gray-500">
        {{ $t('funnel.proposalsSubtitle', 'AI-surfaced trials awaiting physician review. Every decision is audit-logged.') }}
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

    <SkeletonLoader v-if="status === 'pending' && !proposals" variant="cards" />
    <ApiErrorBanner v-else-if="error || proposals?.error" :error="proposals?.error || error?.message" />
    <EmptyState
      v-else-if="!activeProposals.length && !dismissedProposals.length"
      icon="i-lucide-inbox"
      :message="$t('funnel.noProposals', 'No agent proposals yet. ddr_monitor, trial_monitor and funnel_assess post here when they discover new NCTs.')"
    />

    <!-- Active proposals -->
    <div v-if="activeProposals.length" class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div
        v-for="card in activeProposals"
        :key="card.card_id"
        class="rounded-xl border border-indigo-200 bg-indigo-50/40 p-3 space-y-2"
      >
        <div class="flex items-start gap-2">
          <UIcon name="i-lucide-bot" class="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <a
                :href="`https://clinicaltrials.gov/study/${card.nct_id}`"
                target="_blank"
                rel="noopener"
                class="font-mono text-xs text-indigo-800 hover:underline"
              >
                {{ card.nct_id }}
              </a>
              <UBadge
                v-if="card.source_agent"
                variant="subtle"
                size="xs"
                color="neutral"
              >
                {{ card.source_agent }}
              </UBadge>
              <UBadge
                v-if="card.geographic_score !== null && card.geographic_score !== undefined"
                variant="subtle"
                size="xs"
                :color="card.geographic_score >= 0.7 ? 'success' : card.geographic_score >= 0.4 ? 'warning' : 'neutral'"
              >
                geo {{ Math.round((card.geographic_score ?? 0) * 100) }}%
              </UBadge>
            </div>
            <h3 v-if="card.title" class="text-sm text-gray-900 mt-1 line-clamp-2">{{ card.title }}</h3>
          </div>
        </div>

        <div v-if="card.sites_in_scope?.length" class="text-xs text-gray-500">
          <UIcon name="i-lucide-map-pin" class="inline w-3 h-3 mr-0.5" />
          {{ card.sites_in_scope.length }} {{ $t('funnel.siteCount', 'sites') }}
          <span v-if="card.sites_in_scope[0]?.city" class="text-gray-400">
            · {{ card.sites_in_scope.slice(0, 2).map(s => s.city).filter(Boolean).join(' · ') }}
          </span>
        </div>

        <div class="flex items-center gap-1.5 pt-1">
          <UButton
            v-if="canPromote"
            size="xs"
            color="primary"
            variant="solid"
            icon="i-lucide-arrow-up-right"
            @click="openPromote(card)"
          >
            {{ $t('funnel.promote', 'Promote') }}
          </UButton>
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-archive"
            @click="archiveProposal(card)"
          >
            {{ $t('funnel.dismiss', 'Dismiss') }}
          </UButton>
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            :icon="expandedAudit.has(card.card_id) ? 'i-lucide-chevron-up' : 'i-lucide-clock'"
            @click="toggleAudit(card.card_id)"
          >
            {{ $t('funnel.auditLog', 'Audit') }}
          </UButton>
        </div>

        <div v-if="expandedAudit.has(card.card_id)" class="pt-2 border-t border-indigo-200">
          <FunnelAuditLog :card-id="card.card_id" compact />
        </div>
      </div>
    </div>

    <!-- Dismissed (collapsed) -->
    <details v-if="dismissedProposals.length" class="text-xs text-gray-500">
      <summary class="cursor-pointer hover:text-gray-700">
        {{ $t('funnel.dismissedCount', '{n} dismissed proposals', { n: dismissedProposals.length }) }}
      </summary>
      <ul class="mt-2 space-y-1 pl-4">
        <li
          v-for="card in dismissedProposals"
          :key="card.card_id"
          class="font-mono text-xs text-gray-400 line-through"
        >
          {{ card.nct_id }} · {{ card.source_agent }}
        </li>
      </ul>
    </details>

    <!-- Promote dialog -->
    <UModal v-model:open="promoteOpen">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-arrow-up-right" class="w-4 h-4 text-indigo-600" />
              <span class="text-sm font-semibold text-gray-900">
                {{ $t('funnel.promoteDialogTitle', 'Promote proposal to clinical funnel') }}
              </span>
            </div>
          </template>
          <div v-if="promoteCard" class="space-y-3">
            <div class="text-xs text-gray-500">
              <span class="font-mono text-gray-700">{{ promoteCard.nct_id }}</span>
              <span v-if="promoteCard.source_agent" class="ml-2">via {{ promoteCard.source_agent }}</span>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">
                {{ $t('funnel.targetStage', 'Target stage') }}
              </label>
              <USelect
                v-model="promoteStage"
                :items="[...CLINICAL_STAGES]"
                size="sm"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">
                {{ $t('funnel.rationale', 'Rationale (required)') }}
              </label>
              <UTextarea
                v-model="promoteRationale"
                :rows="3"
                :placeholder="$t('funnel.rationalePlaceholder', 'Why is this trial worth tracking now? Cite biomarker / geography / line-of-therapy fit.')"
              />
            </div>
            <div v-if="promoteError" class="text-xs text-red-600">{{ promoteError }}</div>
          </div>
          <template #footer>
            <div class="flex items-center gap-2 justify-end">
              <UButton size="sm" variant="ghost" color="neutral" @click="promoteOpen = false">
                {{ $t('common.cancel', 'Cancel') }}
              </UButton>
              <UButton
                size="sm"
                color="primary"
                :loading="promoteBusy"
                :disabled="!promoteRationale.trim()"
                @click="submitPromote"
              >
                {{ $t('funnel.promote', 'Promote') }}
              </UButton>
            </div>
          </template>
        </UCard>
      </template>
    </UModal>
  </div>
</template>
