<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { activeRole } = useUserRole()

const { data: patient, status: patientStatus, error: patientError } = fetchApi<{
  name: string
  diagnosis_code: string
  diagnosis_description: string
  tumor_site: string
  staging: string
  histology: string
  tumor_laterality: string
  treatment_regimen: string
  current_cycle: number
  ecog: string
  biomarkers: Record<string, string | boolean>
  metastases: string[]
  comorbidities: string[]
  hospitals: string[]
  treating_physician: string
  admitting_physician: string
  excluded_therapies: Array<{ therapy: string; reason: string }> | Record<string, string>
  notes: string
  patient_ids?: Record<string, string>
  active_therapies?: Array<{
    name: string
    drugs: Array<{ name: string; dose: string; lay: string; medical: string }>
    status: string
    warning?: string
    indication?: string
    cycle?: number
  }>
}>('/patient', { lazy: true })

const { data: protocol } = fetchApi<{
  safety_flags: Record<string, { rule: string; source: string }>
}>('/protocol', { lazy: true, timeout: 15000 })

const { data: researchData } = fetchApi<{
  items: Array<{
    id: number
    title: string
    source: string
    external_id: string
    relevance: string
    relevance_reason: string
    summary?: string
    external_url?: string
  }>
}>('/research?limit=5', { lazy: true })

const topStudies = computed(() =>
  (researchData.value?.items ?? []).slice(0, 3)
)

const relevanceBadgeColor: Record<string, string> = {
  high: 'success',
  medium: 'warning',
  low: 'neutral',
}

const biomarkerDisplay = computed(() => {
  if (!patient.value?.biomarkers) return []
  const map: Record<string, string> = {
    KRAS: 'Treatment driver mutation',
    NRAS: '',
    BRAF_V600E: '',
    HER2: '',
    MSI: 'Immunotherapy eligibility marker',
  }
  return Object.entries(patient.value.biomarkers)
    .filter(([key]) => !key.startsWith('anti_') && !key.startsWith('KRAS_G12C'))
    .map(([key, val]) => ({
      name: key.replace(/_/g, ' '),
      value: String(val),
      implication: map[key] || undefined,
    }))
})

const metastasisIcons: Record<string, string> = {
  liver: 'i-lucide-scan',
  peritoneum: 'i-lucide-circle-dot',
  retroperitoneum: 'i-lucide-circle-dot',
  krukenberg: 'i-lucide-circle-alert',
  ovary: 'i-lucide-circle-alert',
  mediastinal: 'i-lucide-activity',
  hilar: 'i-lucide-activity',
  retrocrural: 'i-lucide-activity',
  portal: 'i-lucide-activity',
  pulmonary: 'i-lucide-wind',
}

function getMetIcon(met: string): string {
  const lower = met.toLowerCase()
  for (const [key, icon] of Object.entries(metastasisIcons)) {
    if (lower.includes(key)) return icon
  }
  return 'i-lucide-map-pin'
}

const excludedTherapies = computed(() => {
  const raw = patient.value?.excluded_therapies
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  // Legacy dict format
  return Object.entries(raw).map(([therapy, reason]) => ({ therapy, reason }))
})

const activeTherapies = computed(() =>
  (patient.value?.active_therapies ?? []).filter(t => t.status === 'active' || t.status === 'aktívna')
)

const plannedTherapies = computed(() =>
  (patient.value?.active_therapies ?? []).filter(t => t.status === 'planned' || t.status === 'plánovaná')
)

// Toggle between lay and medical explanations
const showMedical = ref(false)

const drilldown = useDrilldown()

// Medical abbreviation tooltips
const abbreviations: Record<string, string> = {
  ECOG: 'Eastern Cooperative Oncology Group performance status',
  mCRC: 'Metastatic colorectal cancer',
  FOLFOX: 'FOLinic acid + Fluorouracil + OXaliplatin',
  mFOLFOX6: 'Modified FOLFOX6 regimen',
  VJI: 'Vena jugularis interna (internal jugular vein)',
  pMMR: 'Proficient mismatch repair',
  MSS: 'Microsatellite stable',
  G12S: 'Glycine to Serine substitution at position 12',
  KRAS: 'Kirsten rat sarcoma viral oncogene',
  LMWH: 'Low-molecular-weight heparin',
  VTE: 'Venous thromboembolism',
  VEGF: 'Vascular endothelial growth factor',
  DPD: 'Dihydropyrimidine dehydrogenase',
}
</script>

<template>
  <div class="space-y-6">
    <SkeletonLoader v-if="!patient && patientStatus === 'pending'" variant="card" />
    <ApiErrorBanner v-else-if="!patient && patientStatus === 'error'" :error="patientError?.message || 'Failed to load patient data'" />
    <template v-else-if="patient">
    <!-- Patient Header -->
    <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white">{{ patient.name }}</h1>
          <p class="text-sm text-gray-400 mt-1">
            {{ patient.diagnosis_description }} ({{ patient.diagnosis_code }})
          </p>
          <!-- Patient IDs -->
          <div v-if="patient.patient_ids" class="flex items-center gap-4 mt-1.5 text-xs text-gray-500">
            <span v-for="(val, key) in patient.patient_ids" :key="key">
              <span class="text-gray-600">{{ $t(`patient.${key}`, key) }}:</span> {{ val }}
            </span>
          </div>
          <div class="flex items-center gap-3 mt-2 text-xs">
            <UBadge variant="subtle" color="info">{{ $t('patient.stage', { stage: patient.staging?.split(' ')[0] || 'IV' }) }}</UBadge>
            <UBadge variant="subtle" color="neutral">{{ patient.histology }}</UBadge>
            <UBadge variant="subtle" color="neutral">{{ $t('patient.sided', { side: patient.tumor_laterality }) }}</UBadge>
          </div>
        </div>
        <div class="text-right text-sm">
          <div class="text-white font-medium">
            <UTooltip :text="abbreviations['mFOLFOX6']">{{ patient.treatment_regimen }}</UTooltip>
          </div>
          <div class="text-gray-400">{{ $t('patient.cycle', { n: patient.current_cycle }) }}</div>
          <div v-if="patient.ecog" class="text-gray-500 text-xs">
            <UTooltip :text="abbreviations['ECOG']">{{ $t('patient.ecogLabel', { val: patient.ecog }) }}</UTooltip>
          </div>
        </div>
      </div>
    </div>

    <!-- Active Therapies -->
    <div v-if="activeTherapies.length">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.activeTherapies') }}</h2>
      <div class="space-y-3">
        <div
          v-for="(therapy, i) in activeTherapies"
          :key="i"
          class="rounded-xl border border-gray-800 bg-gray-900/50 p-4"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-pill" class="text-teal-500" />
              <span class="text-sm font-medium text-white">{{ therapy.name }}</span>
              <UBadge v-if="therapy.cycle" variant="subtle" color="info" size="xs">
                {{ $t('patient.cycle', { n: therapy.cycle }) }}
              </UBadge>
            </div>
            <button class="text-[10px] text-teal-400 hover:text-teal-300" @click="showMedical = !showMedical">
              {{ showMedical ? $t('patient.layExplanation') : $t('patient.medicalExplanation') }}
            </button>
          </div>
          <div class="space-y-2">
            <div v-for="drug in therapy.drugs" :key="drug.name" class="rounded-lg bg-gray-800/30 px-3 py-2">
              <div class="flex items-center gap-2 text-sm">
                <span class="text-white font-mono text-xs">{{ drug.name }}</span>
                <span class="text-gray-500 text-xs">{{ drug.dose }}</span>
              </div>
              <p class="text-xs text-gray-400 mt-1">{{ showMedical ? drug.medical : drug.lay }}</p>
            </div>
          </div>
          <div v-if="therapy.indication" class="text-xs text-gray-500 mt-2">
            {{ therapy.indication }}
          </div>
        </div>
      </div>
    </div>

    <!-- Planned Therapies (with warnings) -->
    <div v-if="plannedTherapies.length">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.plannedTherapies') }}</h2>
      <div class="space-y-3">
        <div
          v-for="(therapy, i) in plannedTherapies"
          :key="i"
          class="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"
        >
          <div class="flex items-center gap-2 mb-2">
            <UIcon name="i-lucide-alert-triangle" class="text-amber-500" />
            <span class="text-sm font-medium text-white">{{ therapy.name }}</span>
            <UBadge variant="subtle" color="warning" size="xs">{{ therapy.status }}</UBadge>
          </div>
          <div v-if="therapy.warning" class="text-xs text-amber-400 mb-2">{{ therapy.warning }}</div>
          <div class="space-y-2">
            <div v-for="drug in therapy.drugs" :key="drug.name" class="rounded-lg bg-gray-800/30 px-3 py-2">
              <div class="flex items-center gap-2 text-sm">
                <span class="text-white font-mono text-xs">{{ drug.name }}</span>
                <span class="text-gray-500 text-xs">{{ drug.dose }}</span>
              </div>
              <p class="text-xs text-gray-400 mt-1">{{ showMedical ? drug.medical : drug.lay }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Top Studies -->
    <div v-if="topStudies.length">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.topStudies') }}</h2>
      <div class="space-y-2">
        <div
          v-for="study in topStudies"
          :key="study.id"
          class="rounded-xl border border-gray-800 bg-gray-900/50 p-4 cursor-pointer hover:border-gray-600 transition-colors"
          @click="drilldown.open({ type: 'research', id: String(study.id), label: study.title })"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 mb-1">
                <UBadge :color="(relevanceBadgeColor[study.relevance] as any) || 'neutral'" variant="subtle" size="xs">
                  {{ study.relevance }}
                </UBadge>
                <span class="text-xs text-gray-500 uppercase">{{ study.source }}</span>
              </div>
              <p class="text-sm text-white line-clamp-2">{{ study.title }}</p>
              <p v-if="study.relevance_reason" class="text-xs text-gray-500 mt-1">{{ study.relevance_reason }}</p>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <a
                v-if="study.external_url"
                :href="study.external_url"
                target="_blank"
                class="text-teal-500 hover:text-teal-400"
                @click.stop
              >
                <UIcon name="i-lucide-external-link" class="w-4 h-4" />
              </a>
              <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Genomic Profile Cards (hidden for patient role) -->
    <div v-if="activeRole !== 'patient'">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.genomicProfile') }}</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <BiomarkerCard
          v-for="b in biomarkerDisplay"
          :key="b.name"
          :name="b.name"
          :value="b.value"
          :implication="b.implication"
          @drilldown="drilldown.open({ type: 'biomarker', id: b.name, label: b.name })"
        />
      </div>
    </div>

    <!-- Excluded Therapies (hidden for patient role) -->
    <div v-if="excludedTherapies.length && activeRole !== 'patient'">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.excludedTherapies') }}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="(et, i) in excludedTherapies"
          :key="i"
          class="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 cursor-pointer hover:ring-1 hover:ring-red-500/30 transition-all"
          @click="drilldown.open({ type: 'biomarker', id: `excluded-${i}`, label: et.therapy, data: { therapy: et.therapy, reason: et.reason, status: 'Permanently excluded', source: 'Molecular pathology B26/746963' } })"
        >
          <UIcon name="i-lucide-x-circle" class="text-red-500 shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="text-sm text-white truncate">{{ et.therapy }}</div>
            <div class="text-xs text-gray-500">{{ et.reason }}</div>
          </div>
          <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0" />
        </div>
      </div>
    </div>

    <!-- Safety Flags (hidden for patient role) -->
    <div v-if="protocol?.safety_flags && activeRole !== 'patient'">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.safetyFlags') }}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="(flag, id) in protocol.safety_flags"
          :key="id"
          class="cursor-pointer hover:ring-1 hover:ring-teal-500/30 rounded-xl transition-all"
          @click="drilldown.open({ type: 'protocol_section', id: `safety-${id}`, label: String(id).replace(/_/g, ' '), data: { flag: String(id), rule: flag.rule, source: flag.source, severity: flag.rule.includes('NEVER') ? 'critical' : 'warning' } })"
        >
          <SafetyFlag :id="String(id)" :rule="flag.rule" :source="flag.source" />
        </div>
      </div>
    </div>

    <!-- Metastases -->
    <div v-if="patient.metastases?.length">
      <h2 class="text-lg font-semibold text-white mb-3">{{ $t('patient.metastases') }}</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
        <div
          v-for="(met, i) in patient.metastases"
          :key="i"
          class="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/50 px-3 py-2 cursor-pointer hover:border-gray-600 transition-colors"
          @click="drilldown.open({ type: 'patient', id: `met-${i}`, label: met, data: { site: met, type: 'Metastasis', source: 'CT staging / pathology' } })"
        >
          <UIcon :name="getMetIcon(met)" class="text-gray-500 shrink-0" />
          <span class="text-sm text-gray-300 flex-1">{{ met }}</span>
          <UIcon name="i-lucide-chevron-right" class="w-3 h-3 text-gray-700 shrink-0" />
        </div>
      </div>
    </div>

    <!-- Treatment Info -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h3 class="text-sm font-semibold text-white mb-2">{{ $t('patient.hospitals') }}</h3>
        <div v-for="h in patient.hospitals" :key="h" class="text-sm text-gray-400 flex items-center gap-2 py-1">
          <UIcon name="i-lucide-building-2" class="text-gray-600" />
          {{ h }}
        </div>
      </div>
      <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h3 class="text-sm font-semibold text-white mb-2">{{ $t('patient.physicians') }}</h3>
        <div v-if="patient.treating_physician" class="text-sm text-gray-400 py-1">
          <span class="text-gray-600">{{ $t('patient.treating') }}</span> {{ patient.treating_physician }}
        </div>
        <div v-if="patient.admitting_physician" class="text-sm text-gray-400 py-1">
          <span class="text-gray-600">{{ $t('patient.admitting') }}</span> {{ patient.admitting_physician }}
        </div>
      </div>
    </div>

    <!-- Comorbidities & Notes -->
    <div v-if="patient.comorbidities?.length || patient.notes" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <h3 class="text-sm font-semibold text-white mb-2">{{ $t('patient.notesComorbidities') }}</h3>
      <div v-for="c in patient.comorbidities" :key="c" class="text-sm text-amber-400 flex items-center gap-2 py-1">
        <UIcon name="i-lucide-alert-circle" class="shrink-0" />
        {{ c }}
      </div>
      <p v-if="patient.notes" class="text-sm text-gray-400 mt-2">{{ patient.notes }}</p>
    </div>
    </template>
  </div>
</template>
