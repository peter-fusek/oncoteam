<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: protocol, refresh } = await fetchApi<{
  lab_thresholds: Record<string, { min?: number; max_ratio?: number; unit?: string; note?: string; action: string }>
  dose_modifications: Record<string, string>
  milestones: Array<{ cycle: number; action: string; description: string }>
  monitoring_schedule: Record<string, string>
  safety_flags: Record<string, { rule: string; source: string }>
  second_line_options: Array<{ regimen: string; evidence: string; note: string }>
  watched_trials: string[]
  current_cycle: number
}>('/protocol')

const activeTab = ref('checklist')
const tabs = [
  { key: 'checklist', label: 'Pre-Cycle Checklist', icon: 'i-lucide-clipboard-check' },
  { key: 'labs', label: 'Lab Thresholds', icon: 'i-lucide-test-tube-diagonal' },
  { key: 'dosemods', label: 'Dose Modifications', icon: 'i-lucide-pill' },
  { key: 'milestones', label: 'Milestones', icon: 'i-lucide-milestone' },
  { key: 'monitoring', label: 'Monitoring', icon: 'i-lucide-calendar' },
  { key: '2l', label: '2L Options', icon: 'i-lucide-arrow-right-circle' },
  { key: 'trials', label: 'Watched Trials', icon: 'i-lucide-eye' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Clinical Protocol</h1>
        <p class="text-sm text-gray-400">mFOLFOX6 treatment protocol and guidelines</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <!-- Tab navigation -->
    <div class="flex gap-2 flex-wrap">
      <UButton
        v-for="tab in tabs"
        :key="tab.key"
        :icon="tab.icon"
        :variant="activeTab === tab.key ? 'solid' : 'ghost'"
        :color="activeTab === tab.key ? 'primary' : 'neutral'"
        size="xs"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </UButton>
    </div>

    <div v-if="protocol">
      <!-- Pre-Cycle Checklist -->
      <div v-if="activeTab === 'checklist'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <PreCycleChecklist :current-cycle="protocol.current_cycle" />
      </div>

      <!-- Lab Thresholds -->
      <div v-if="activeTab === 'labs'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">Pre-Cycle Lab Safety Thresholds</h2>
        <LabThresholdTable :thresholds="protocol.lab_thresholds" />
      </div>

      <!-- Dose Modifications -->
      <div v-if="activeTab === 'dosemods'" class="space-y-2">
        <DoseModCard
          v-for="(action, toxicity) in protocol.dose_modifications"
          :key="toxicity"
          :toxicity="toxicity"
          :action="action"
        />
      </div>

      <!-- Milestones -->
      <div v-if="activeTab === 'milestones'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">Treatment Milestones</h2>
        <MilestoneTracker :milestones="protocol.milestones" :current-cycle="protocol.current_cycle" />
      </div>

      <!-- Monitoring Schedule -->
      <div v-if="activeTab === 'monitoring'" class="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 class="text-sm font-semibold text-white mb-4">Monitoring Schedule</h2>
        <div class="space-y-2">
          <div
            v-for="(schedule, item) in protocol.monitoring_schedule"
            :key="item"
            class="flex items-start gap-3 py-2 border-b border-gray-800/50 last:border-0"
          >
            <UIcon name="i-lucide-clock" class="text-gray-600 mt-0.5 shrink-0" />
            <div>
              <div class="text-sm text-white">{{ item.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()) }}</div>
              <div class="text-xs text-gray-500">{{ schedule }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Second-Line Options -->
      <div v-if="activeTab === '2l'" class="space-y-2">
        <div
          v-for="(opt, i) in protocol.second_line_options"
          :key="i"
          class="rounded-lg border border-gray-800 bg-gray-900/50 p-4"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-white">{{ i + 1 }}.</span>
            <span class="text-sm font-medium text-white">{{ opt.regimen }}</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">{{ opt.evidence }}</div>
          <div class="text-xs text-gray-500 mt-0.5 italic">{{ opt.note }}</div>
        </div>
      </div>

      <!-- Watched Trials -->
      <div v-if="activeTab === 'trials'" class="space-y-2">
        <div
          v-for="trial in protocol.watched_trials"
          :key="trial"
          class="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3"
        >
          <UIcon name="i-lucide-eye" class="text-teal-500 shrink-0" />
          <span class="text-sm text-gray-300">{{ trial }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
