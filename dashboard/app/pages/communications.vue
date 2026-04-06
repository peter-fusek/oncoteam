<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()

// Fetch all communication sources in parallel
const { data: briefingsData } = fetchApi<{
  briefings: Array<{ id: number; title: string; content: string; date: string; type: string; tags: string[] }>
}>('/briefings?limit=10', { lazy: true, server: false })

const { data: familyData } = fetchApi<{
  updates: Array<{ id: number; title: string; content: string; date: string; tags: string[] }>
}>('/family-update', { lazy: true, server: false })

const { data: sessionsData } = fetchApi<{
  sessions: Array<{ id: number; title: string; content: string; date: string | null; session_type: string }>
}>('/sessions?limit=20', { lazy: true, server: false })

const channelFilter = ref<'all' | 'briefing' | 'family' | 'session'>('all')

interface CommEntry {
  id: number
  channel: 'briefing' | 'family' | 'session'
  title: string
  content: string
  date: string
  icon: string
  color: string
}

const allComms = computed<CommEntry[]>(() => {
  const entries: CommEntry[] = []

  for (const b of briefingsData.value?.briefings ?? []) {
    entries.push({
      id: b.id, channel: 'briefing', title: b.title, content: b.content,
      date: b.date, icon: 'i-lucide-bot', color: 'text-teal-600',
    })
  }
  for (const f of familyData.value?.updates ?? []) {
    entries.push({
      id: f.id, channel: 'family', title: f.title, content: f.content,
      date: f.date, icon: 'i-lucide-heart', color: 'text-pink-600',
    })
  }
  for (const s of sessionsData.value?.sessions ?? []) {
    entries.push({
      id: s.id, channel: 'session', title: s.title, content: s.content || '',
      date: s.date || '', icon: 'i-lucide-message-square', color: 'text-blue-600',
    })
  }

  entries.sort((a, b) => b.date.localeCompare(a.date))
  return entries
})

const filteredComms = computed(() => {
  if (channelFilter.value === 'all') return allComms.value
  return allComms.value.filter(c => c.channel === channelFilter.value)
})

const channelCounts = computed(() => ({
  briefing: allComms.value.filter(c => c.channel === 'briefing').length,
  family: allComms.value.filter(c => c.channel === 'family').length,
  session: allComms.value.filter(c => c.channel === 'session').length,
}))

const drilldown = useDrilldown()

function openComm(entry: CommEntry) {
  const type = entry.channel === 'briefing' ? 'conversation' : entry.channel === 'family' ? 'document' : 'conversation'
  drilldown.open({ type, id: entry.id, label: entry.title, data: { title: entry.title, content: entry.content, date: entry.date, channel: entry.channel } })
}

const channelLabel: Record<string, string> = {
  briefing: 'Agent Briefing',
  family: 'Family Update',
  session: 'Session',
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('communications.title') }}</h1>
        <p class="text-sm text-gray-500">{{ $t('communications.subtitle', { count: allComms.length }) }}</p>
      </div>
    </div>

    <!-- Channel filter -->
    <div class="flex gap-2">
      <UButton size="xs" :variant="channelFilter === 'all' ? 'solid' : 'ghost'" :color="channelFilter === 'all' ? 'primary' : 'neutral'" @click="channelFilter = 'all'">
        {{ $t('sessions.filterAll') }} ({{ allComms.length }})
      </UButton>
      <UButton size="xs" :variant="channelFilter === 'briefing' ? 'solid' : 'ghost'" :color="channelFilter === 'briefing' ? 'primary' : 'neutral'" @click="channelFilter = 'briefing'">
        <UIcon name="i-lucide-bot" class="w-3 h-3 mr-0.5" /> Briefings ({{ channelCounts.briefing }})
      </UButton>
      <UButton size="xs" :variant="channelFilter === 'family' ? 'solid' : 'ghost'" :color="channelFilter === 'family' ? 'primary' : 'neutral'" @click="channelFilter = 'family'">
        <UIcon name="i-lucide-heart" class="w-3 h-3 mr-0.5" /> Family ({{ channelCounts.family }})
      </UButton>
      <UButton size="xs" :variant="channelFilter === 'session' ? 'solid' : 'ghost'" :color="channelFilter === 'session' ? 'primary' : 'neutral'" @click="channelFilter = 'session'">
        <UIcon name="i-lucide-message-square" class="w-3 h-3 mr-0.5" /> Sessions ({{ channelCounts.session }})
      </UButton>
    </div>

    <SkeletonLoader v-if="!briefingsData && !familyData && !sessionsData" variant="cards" />

    <div v-if="filteredComms.length" class="space-y-2">
      <div
        v-for="entry in filteredComms"
        :key="`${entry.channel}-${entry.id}`"
        class="rounded-lg border border-gray-200 bg-white p-4 cursor-pointer hover:ring-1 hover:ring-teal-500/30 transition-all"
        @click="openComm(entry)"
      >
        <div class="flex items-start gap-3">
          <UIcon :name="entry.icon" :class="entry.color" class="w-4 h-4 mt-0.5 shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-sm font-medium text-gray-900 truncate">{{ entry.title }}</span>
              <UBadge variant="subtle" size="xs" color="neutral">{{ channelLabel[entry.channel] }}</UBadge>
            </div>
            <p class="text-xs text-gray-500 line-clamp-2">{{ entry.content }}</p>
          </div>
          <span class="text-xs text-gray-400 shrink-0">{{ formatDate(entry.date) }}</span>
        </div>
      </div>
    </div>

    <div v-else-if="allComms.length === 0" class="text-gray-400 text-center py-16 text-sm">
      {{ $t('communications.noData') }}
    </div>
  </div>
</template>
