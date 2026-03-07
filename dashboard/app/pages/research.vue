<script setup lang="ts">
const { fetchApi } = useOncoteamApi()

const { data: research, refresh } = await fetchApi<{
  entries: Array<{
    id: number
    source: string
    external_id: string
    title: string
    summary: string
    date: string | null
  }>
  total: number
}>('/research?limit=50')

const sourceFilter = ref<string | null>(null)

const filtered = computed(() => {
  if (!research.value?.entries) return []
  if (!sourceFilter.value) return research.value.entries
  return research.value.entries.filter(e => e.source === sourceFilter.value)
})

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Research Log</h1>
        <p class="text-sm text-gray-400">{{ research?.total ?? 0 }} entries found</p>
      </div>
      <div class="flex items-center gap-2">
        <UButtonGroup>
          <UButton
            :variant="!sourceFilter ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="sourceFilter = null"
          >
            All
          </UButton>
          <UButton
            :variant="sourceFilter === 'pubmed' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="sourceFilter = 'pubmed'"
          >
            PubMed
          </UButton>
          <UButton
            :variant="sourceFilter === 'clinicaltrials' ? 'solid' : 'ghost'"
            size="xs"
            color="neutral"
            @click="sourceFilter = 'clinicaltrials'"
          >
            Trials
          </UButton>
        </UButtonGroup>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <div v-if="filtered.length" class="space-y-2">
      <div
        v-for="entry in filtered"
        :key="entry.id"
        class="rounded-lg border border-gray-800 bg-gray-900/50 p-4 hover:bg-gray-800/30 transition-colors cursor-pointer hover:ring-1 hover:ring-teal-500/30"
        @click="drilldown.open({ type: 'research', id: entry.id, label: entry.title })"
      >
        <div class="flex items-start gap-3">
          <span class="text-lg mt-0.5">{{ entry.source === 'pubmed' ? '📄' : '🧪' }}</span>
          <div class="min-w-0 flex-1">
            <div class="font-medium text-white text-sm">{{ entry.title }}</div>
            <div class="flex items-center gap-2 mt-1.5">
              <UBadge
                variant="subtle"
                size="xs"
                :color="entry.source === 'pubmed' ? 'info' : 'success'"
              >
                {{ entry.source }}
              </UBadge>
              <span v-if="entry.external_id" class="text-xs font-mono text-gray-500">
                {{ entry.external_id }}
              </span>
            </div>
            <p v-if="entry.summary" class="text-xs text-gray-500 mt-2 line-clamp-2">
              {{ entry.summary }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="text-gray-600 text-center py-16 text-sm">
      No research entries found
    </div>
  </div>
</template>
