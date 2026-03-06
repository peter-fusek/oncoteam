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

const sourceOptions = [
  { label: 'All', value: null },
  { label: 'PubMed', value: 'pubmed' },
  { label: 'ClinicalTrials.gov', value: 'clinicaltrials' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Research Log</h1>
      <div class="flex items-center gap-2">
        <UButtonGroup>
          <UButton
            v-for="opt in sourceOptions"
            :key="String(opt.value)"
            :variant="sourceFilter === opt.value ? 'solid' : 'ghost'"
            size="sm"
            @click="sourceFilter = opt.value"
          >
            {{ opt.label }}
          </UButton>
        </UButtonGroup>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="sm" @click="refresh" />
      </div>
    </div>

    <div v-if="filtered.length" class="space-y-3">
      <UCard v-for="entry in filtered" :key="entry.id">
        <div class="flex items-start gap-3">
          <UIcon
            :name="entry.source === 'pubmed' ? 'i-lucide-book-open' : 'i-lucide-flask-conical'"
            class="mt-1 shrink-0"
            :class="entry.source === 'pubmed' ? 'text-blue-500' : 'text-green-500'"
          />
          <div class="min-w-0 flex-1">
            <div class="font-medium">{{ entry.title }}</div>
            <div class="text-sm text-muted mt-1 flex gap-3">
              <UBadge variant="subtle" size="xs">{{ entry.source }}</UBadge>
              <span v-if="entry.external_id" class="font-mono">{{ entry.external_id }}</span>
              <span v-if="entry.date">{{ entry.date.split('T')[0] }}</span>
            </div>
            <p v-if="entry.summary" class="text-sm text-muted mt-2 line-clamp-2">
              {{ entry.summary }}
            </p>
          </div>
        </div>
      </UCard>
    </div>

    <div v-else class="text-muted text-center py-12">
      No research entries found
    </div>
  </div>
</template>
