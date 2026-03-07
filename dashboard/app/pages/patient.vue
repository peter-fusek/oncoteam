<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: patient } = await fetchApi<{
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
  excluded_therapies: Record<string, string>
  notes: string
}>('/patient')

const { data: protocol } = await fetchApi<{
  safety_flags: Record<string, { rule: string; source: string }>
}>('/protocol')

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
</script>

<template>
  <div v-if="patient" class="space-y-6">
    <!-- Patient Header -->
    <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-2xl font-bold text-white">{{ patient.name }}</h1>
          <p class="text-sm text-gray-400 mt-1">
            {{ patient.diagnosis_description }} ({{ patient.diagnosis_code }})
          </p>
          <div class="flex items-center gap-3 mt-2 text-xs">
            <UBadge variant="subtle" color="info">Stage {{ patient.staging?.split(' ')[0] || 'IV' }}</UBadge>
            <UBadge variant="subtle" color="neutral">{{ patient.histology }}</UBadge>
            <UBadge variant="subtle" color="neutral">{{ patient.tumor_laterality }}-sided</UBadge>
          </div>
        </div>
        <div class="text-right text-sm">
          <div class="text-white font-medium">{{ patient.treatment_regimen }}</div>
          <div class="text-gray-400">Cycle {{ patient.current_cycle }}</div>
          <div v-if="patient.ecog" class="text-gray-500 text-xs">ECOG: {{ patient.ecog }}</div>
        </div>
      </div>
    </div>

    <!-- Genomic Profile Cards -->
    <div>
      <h2 class="text-lg font-semibold text-white mb-3">Genomic Profile</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <BiomarkerCard
          v-for="b in biomarkerDisplay"
          :key="b.name"
          :name="b.name"
          :value="b.value"
          :implication="b.implication"
        />
      </div>
    </div>

    <!-- Excluded Therapies -->
    <div v-if="patient.excluded_therapies">
      <h2 class="text-lg font-semibold text-white mb-3">Excluded Therapies</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="(reason, therapy) in patient.excluded_therapies"
          :key="therapy"
          class="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2"
        >
          <UIcon name="i-lucide-x-circle" class="text-red-500 shrink-0" />
          <div class="min-w-0">
            <div class="text-sm text-white truncate">{{ therapy }}</div>
            <div class="text-xs text-gray-500">{{ reason }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Safety Flags -->
    <div v-if="protocol?.safety_flags">
      <h2 class="text-lg font-semibold text-white mb-3">Safety Flags</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <SafetyFlag
          v-for="(flag, id) in protocol.safety_flags"
          :key="id"
          :id="String(id)"
          :rule="flag.rule"
          :source="flag.source"
        />
      </div>
    </div>

    <!-- Metastases -->
    <div v-if="patient.metastases?.length">
      <h2 class="text-lg font-semibold text-white mb-3">Metastases</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
        <div
          v-for="met in patient.metastases"
          :key="met"
          class="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/50 px-3 py-2"
        >
          <UIcon :name="getMetIcon(met)" class="text-gray-500 shrink-0" />
          <span class="text-sm text-gray-300">{{ met }}</span>
        </div>
      </div>
    </div>

    <!-- Treatment Info -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h3 class="text-sm font-semibold text-white mb-2">Hospitals</h3>
        <div v-for="h in patient.hospitals" :key="h" class="text-sm text-gray-400 flex items-center gap-2 py-1">
          <UIcon name="i-lucide-building-2" class="text-gray-600" />
          {{ h }}
        </div>
      </div>
      <div class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
        <h3 class="text-sm font-semibold text-white mb-2">Physicians</h3>
        <div v-if="patient.treating_physician" class="text-sm text-gray-400 py-1">
          <span class="text-gray-600">Treating:</span> {{ patient.treating_physician }}
        </div>
        <div v-if="patient.admitting_physician" class="text-sm text-gray-400 py-1">
          <span class="text-gray-600">Admitting:</span> {{ patient.admitting_physician }}
        </div>
      </div>
    </div>

    <!-- Comorbidities & Notes -->
    <div v-if="patient.comorbidities?.length || patient.notes" class="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <h3 class="text-sm font-semibold text-white mb-2">Notes & Comorbidities</h3>
      <div v-for="c in patient.comorbidities" :key="c" class="text-sm text-amber-400 flex items-center gap-2 py-1">
        <UIcon name="i-lucide-alert-circle" class="shrink-0" />
        {{ c }}
      </div>
      <p v-if="patient.notes" class="text-sm text-gray-400 mt-2">{{ patient.notes }}</p>
    </div>
  </div>
</template>
