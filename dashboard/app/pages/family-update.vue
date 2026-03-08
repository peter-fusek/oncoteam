<script setup lang="ts">
const { fetchApi, apiUrl } = useOncoteamApi()

const lang = ref<'sk' | 'en'>('sk')

const { data: updates, refresh } = await fetchApi<{
  updates: Array<{
    id: number
    title: string
    content: string
    date: string
    tags: string[]
  }>
  total: number
  error?: string
}>('/family-update')

const generating = ref(false)
const latestGenerated = ref('')

async function generateUpdate() {
  generating.value = true
  latestGenerated.value = ''
  try {
    const result = await $fetch<{ created: boolean; content: string; lang: string }>(
      apiUrl('/family-update'),
      {
        method: 'POST',
        body: { lang: lang.value },
      },
    )
    latestGenerated.value = result.content
    await refresh()
  } catch (e: any) {
    latestGenerated.value = `Error: ${e.message || e}`
  } finally {
    generating.value = false
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
}

function printUpdate() {
  window.print()
}

const drilldown = useDrilldown()
</script>

<template>
  <div class="space-y-6 print:space-y-4 print:text-black">
    <div class="flex items-center justify-between print:hidden">
      <div>
        <h1 class="text-2xl font-bold text-white">Family Update</h1>
        <p class="text-sm text-gray-400">Plain-language summary for family members</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Language toggle -->
        <div class="flex rounded-lg border border-gray-700 overflow-hidden">
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="lang === 'sk' ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
            @click="lang = 'sk'"
          >
            SK
          </button>
          <button
            class="px-3 py-1.5 text-xs font-medium transition-colors"
            :class="lang === 'en' ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
            @click="lang = 'en'"
          >
            EN
          </button>
        </div>
        <UButton
          :loading="generating"
          icon="i-lucide-sparkles"
          color="primary"
          size="xs"
          @click="generateUpdate"
        >
          Generate
        </UButton>
        <UButton icon="i-lucide-printer" variant="outline" size="xs" color="neutral" @click="printUpdate">
          Print
        </UButton>
        <UButton icon="i-lucide-refresh-cw" variant="ghost" size="xs" color="neutral" @click="refresh" />
      </div>
    </div>

    <ApiErrorBanner :error="updates?.error" />

    <!-- Print header -->
    <div class="hidden print:block">
      <h1 class="text-xl font-bold">Oncoteam — {{ lang === 'sk' ? 'Správa pre rodinu' : 'Family Update' }}</h1>
      <p class="text-sm text-gray-500">{{ new Date().toLocaleDateString('sk-SK') }}</p>
    </div>

    <!-- Latest generated update -->
    <div v-if="latestGenerated" class="rounded-xl border border-teal-500/30 bg-teal-500/5 p-5 print:border-gray-300 print:bg-white">
      <div class="flex items-center justify-between mb-3 print:hidden">
        <h2 class="text-sm font-semibold text-white">
          {{ lang === 'sk' ? 'Nová správa' : 'New Update' }}
        </h2>
        <UButton
          icon="i-lucide-copy"
          variant="ghost"
          size="xs"
          color="neutral"
          @click="copyToClipboard(latestGenerated)"
        />
      </div>
      <div class="prose prose-sm prose-invert max-w-none print:prose-gray">
        <p
          v-for="(line, i) in latestGenerated.split('\n').filter(l => l.trim())"
          :key="i"
          class="text-gray-300 print:text-black leading-relaxed"
        >
          {{ line }}
        </p>
      </div>
    </div>

    <!-- Past updates -->
    <div v-if="updates?.updates?.length" class="space-y-3">
      <h2 class="text-sm font-semibold text-white print:text-black">
        {{ lang === 'sk' ? 'Predchádzajúce správy' : 'Previous Updates' }}
      </h2>
      <div
        v-for="update in updates.updates"
        :key="update.id"
        class="rounded-xl border border-gray-800 bg-gray-900/50 p-4 print:border-gray-300 print:bg-white"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-white print:text-black">{{ update.title }}</span>
          <div class="flex items-center gap-2 print:hidden">
            <UBadge
              v-if="update.tags?.some((t: string) => t.includes('lang:'))"
              variant="subtle"
              size="xs"
              color="info"
            >
              {{ update.tags?.find((t: string) => t.startsWith('lang:'))?.replace('lang:', '').toUpperCase() }}
            </UBadge>
            <span class="text-xs text-gray-500">{{ update.date }}</span>
            <UButton
              icon="i-lucide-copy"
              variant="ghost"
              size="xs"
              color="neutral"
              @click="copyToClipboard(update.content)"
            />
          </div>
        </div>
        <div class="text-sm text-gray-300 print:text-black leading-relaxed whitespace-pre-line">
          {{ update.content }}
        </div>
      </div>
    </div>

    <div v-else-if="!updates?.error && !latestGenerated" class="text-gray-600 text-center py-8 text-sm">
      {{ lang === 'sk' ? 'Zatiaľ žiadne správy — klikni na Generovať' : 'No updates yet — click Generate' }}
    </div>
  </div>
</template>
