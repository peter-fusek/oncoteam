<script setup lang="ts">
import { MEDICAL_DICTIONARY, CATEGORY_LABELS, searchDictionary } from '~/data/medical-dictionary'
import type { DictionaryEntry } from '~/data/medical-dictionary'

const { t, locale } = useI18n()
const route = useRoute()

const searchQuery = ref((route.query.q as string) || '')
const selectedCategory = ref<string | null>(null)
const mode = ref<'pro' | 'laik'>('laik')

const lang = computed(() => locale.value as 'sk' | 'en')

const filteredEntries = computed(() => {
  let entries = searchDictionary(searchQuery.value)
  if (selectedCategory.value) {
    entries = entries.filter((e) => e.category === selectedCategory.value)
  }
  return entries
})

const categories = computed(() => {
  const cats = [...new Set(MEDICAL_DICTIONARY.map((e) => e.category))]
  return cats.map((c) => ({
    key: c,
    label: CATEGORY_LABELS[c]?.[lang.value] || c,
    count: MEDICAL_DICTIONARY.filter((e) => e.category === c).length,
  }))
})

function getDescription(entry: DictionaryEntry): string {
  return mode.value === 'pro' ? entry.proDesc[lang.value] : entry.laikDesc[lang.value]
}

function getCategoryColor(cat: string): string {
  const colors: Record<string, string> = {
    lab: 'bg-blue-500/20 text-blue-400',
    tumor_marker: 'bg-orange-500/20 text-orange-400',
    treatment: 'bg-green-500/20 text-green-400',
    diagnosis: 'bg-purple-500/20 text-purple-400',
    inflammation: 'bg-red-500/20 text-red-400',
    general: 'bg-gray-500/20 text-gray-400',
  }
  return colors[cat] || 'bg-gray-500/20 text-gray-400'
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-white">{{ t('dictionary.title') }}</h1>
      <p class="text-sm text-gray-400 mt-1">{{ t('dictionary.subtitle') }}</p>
    </div>

    <!-- Controls -->
    <div class="flex flex-col sm:flex-row gap-3">
      <!-- Search -->
      <div class="relative flex-1">
        <UIcon name="i-lucide-search" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          v-model="searchQuery"
          :placeholder="t('dictionary.search')"
          class="w-full pl-10 pr-4 py-2 rounded-lg bg-gray-900 border border-gray-700 text-sm text-white placeholder-gray-500 focus:border-teal-500 focus:outline-none"
        />
      </div>

      <!-- Pro/Laik toggle -->
      <div class="flex rounded-lg border border-gray-700 overflow-hidden">
        <button
          class="px-3 py-2 text-xs font-medium transition-colors"
          :class="mode === 'laik' ? 'bg-teal-600 text-white' : 'bg-gray-900 text-gray-400 hover:text-white'"
          @click="mode = 'laik'"
        >
          {{ t('dictionary.simple') }}
        </button>
        <button
          class="px-3 py-2 text-xs font-medium transition-colors"
          :class="mode === 'pro' ? 'bg-teal-600 text-white' : 'bg-gray-900 text-gray-400 hover:text-white'"
          @click="mode = 'pro'"
        >
          {{ t('dictionary.professional') }}
        </button>
      </div>
    </div>

    <!-- Category pills -->
    <div class="flex flex-wrap gap-2">
      <button
        class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
        :class="selectedCategory === null ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
        @click="selectedCategory = null"
      >
        {{ t('dictionary.all') }} ({{ MEDICAL_DICTIONARY.length }})
      </button>
      <button
        v-for="cat in categories"
        :key="cat.key"
        class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
        :class="selectedCategory === cat.key ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'"
        @click="selectedCategory = selectedCategory === cat.key ? null : cat.key"
      >
        {{ cat.label }} ({{ cat.count }})
      </button>
    </div>

    <!-- Results count -->
    <p class="text-xs text-gray-500">
      {{ filteredEntries.length }} {{ t('dictionary.results') }}
    </p>

    <!-- Dictionary grid -->
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="entry in filteredEntries"
        :key="entry.abbr"
        class="rounded-xl border border-gray-800 bg-gray-900/50 p-4 hover:border-gray-700 transition-colors"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-2">
          <div>
            <span class="text-lg font-bold text-teal-400">{{ entry.abbr }}</span>
            <p class="text-xs text-gray-400 mt-0.5">{{ entry.fullName[lang] }}</p>
          </div>
          <span
            class="px-2 py-0.5 rounded-full text-[10px] font-medium"
            :class="getCategoryColor(entry.category)"
          >
            {{ CATEGORY_LABELS[entry.category]?.[lang] || entry.category }}
          </span>
        </div>

        <!-- Description -->
        <p class="text-sm text-gray-300 leading-relaxed">{{ getDescription(entry) }}</p>

        <!-- Reference range -->
        <div v-if="entry.referenceRange || entry.unit" class="mt-3 pt-2 border-t border-gray-800 flex items-center gap-3">
          <span v-if="entry.referenceRange" class="text-xs text-gray-500">
            {{ t('dictionary.range') }}: <span class="text-gray-300">{{ entry.referenceRange }}</span>
          </span>
          <span v-if="entry.unit" class="text-xs text-gray-500">
            {{ t('dictionary.unit') }}: <span class="text-gray-300">{{ entry.unit }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="filteredEntries.length === 0" class="text-center py-12">
      <UIcon name="i-lucide-search-x" class="w-12 h-12 text-gray-600 mx-auto mb-3" />
      <p class="text-sm text-gray-500">{{ t('dictionary.noResults') }}</p>
    </div>
  </div>
</template>
