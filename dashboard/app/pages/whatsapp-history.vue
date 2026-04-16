<script setup lang="ts">
const { fetchApi } = useOncoteamApi()
const { formatDate } = useFormatDate()
const { t } = useI18n()

const searchQuery = ref('')
const debouncedSearch = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = val }, 400)
})

const apiQuery = computed(() => {
  const q: Record<string, string> = { limit: '100' }
  if (debouncedSearch.value.length >= 2) q.search = debouncedSearch.value
  return q
})

const { data, status, error: fetchError, refresh } = fetchApi<{
  messages: Array<{
    id: number
    date: string
    phone_masked: string
    user_message: string
    bot_response: string
    title: string
    tags: string[]
  }>
  total: number
  error?: string
}>(() => '/whatsapp/history', {
  query: apiQuery,
  lazy: true,
  server: false,
  watch: [debouncedSearch],
  dedupe: 'cancel',
})

const messages = computed(() => data.value?.messages ?? [])

function isVoice(tags: string[]): boolean {
  return tags?.some(t => t.includes('voice')) ?? false
}

function isCommand(title: string): boolean {
  return title?.startsWith('WhatsApp: /') ?? false
}

function formatTime(dateStr: string): string {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleString('sk-SK', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  catch { return dateStr }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ t('whatsapp.title') }}</h1>
        <p class="text-sm text-gray-500">{{ t('whatsapp.subtitle', { count: data?.total ?? 0 }) }}</p>
      </div>
      <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
    </div>

    <!-- Search -->
    <div class="relative max-w-md">
      <UIcon name="i-lucide-search" class="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="t('whatsapp.searchPlaceholder')"
        class="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[var(--clinical-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--clinical-primary)]"
      >
    </div>

    <ApiErrorBanner :error="data?.error || fetchError?.message" />
    <SkeletonLoader v-if="!data && status === 'pending'" variant="cards" />

    <!-- Messages list -->
    <div v-if="messages.length" class="space-y-3">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="rounded-xl border border-gray-200 bg-white p-4"
      >
        <!-- Header row -->
        <div class="flex items-center gap-2 mb-3 text-xs text-gray-500">
          <span class="font-mono">{{ formatTime(msg.date) }}</span>
          <UBadge variant="subtle" size="xs" color="neutral">
            {{ msg.phone_masked }}
          </UBadge>
          <UBadge v-if="isVoice(msg.tags)" variant="subtle" size="xs" color="info">
            <UIcon name="i-lucide-mic" class="w-3 h-3 mr-0.5" />
            {{ t('whatsapp.voice') }}
          </UBadge>
          <UBadge v-if="isCommand(msg.title)" variant="subtle" size="xs" color="success">
            <UIcon name="i-lucide-terminal" class="w-3 h-3 mr-0.5" />
            {{ t('whatsapp.command') }}
          </UBadge>
        </div>

        <!-- Chat bubbles -->
        <div class="space-y-2">
          <!-- User message -->
          <div class="flex justify-end">
            <div class="max-w-[80%] rounded-xl rounded-br-sm bg-[var(--clinical-primary)] px-3 py-2 text-sm text-white">
              {{ msg.user_message }}
            </div>
          </div>
          <!-- Bot response -->
          <div v-if="msg.bot_response" class="flex justify-start">
            <div class="max-w-[80%] rounded-xl rounded-bl-sm bg-gray-100 px-3 py-2 text-sm text-gray-900 whitespace-pre-line">
              {{ msg.bot_response }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!data?.error && !fetchError && status !== 'pending'" class="text-gray-400 text-center py-16 text-sm">
      {{ debouncedSearch ? t('whatsapp.noResults') : t('whatsapp.noMessages') }}
    </div>
  </div>
</template>
