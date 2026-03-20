<script setup lang="ts">
defineProps<{
  title: string
  content: string
  date: string
  tags?: string[] | string
  summary?: string
  actionCount?: number
}>()

defineEmits<{ drilldown: [] }>()

const expanded = ref(false)

function formatTags(tags: string[] | string | undefined): string[] {
  if (!tags) return []
  if (typeof tags === 'string') return tags.split(',').map(t => t.trim())
  return tags
}
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white overflow-hidden">
    <button
      class="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
      @click="expanded = !expanded"
    >
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium text-gray-900 truncate">{{ title }}</div>
        <div v-if="summary && !expanded" class="text-xs text-gray-500 mt-1 line-clamp-2">
          {{ summary }}
        </div>
        <div class="flex items-center gap-2 mt-1">
          <span class="text-xs text-gray-500">
            {{ new Date(date).toLocaleString('sk-SK', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) }}
          </span>
          <UBadge v-if="actionCount" variant="subtle" size="xs" color="warning">
            {{ $t('briefings.actionItems', { count: actionCount }) }}
          </UBadge>
        </div>
      </div>
      <div class="flex items-center gap-2 ml-3 shrink-0">
        <UBadge v-for="tag in formatTags(tags)" :key="tag" variant="subtle" size="xs" color="neutral">{{ tag }}</UBadge>
        <UIcon :name="expanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" class="text-gray-500" />
      </div>
    </button>
    <div v-if="expanded" class="px-4 pb-4 border-t border-gray-200">
      <div class="prose prose-sm prose-gray max-w-none mt-3 text-sm text-gray-700 whitespace-pre-wrap">{{ content }}</div>
      <button
        class="mt-3 text-xs text-teal-600 hover:text-teal-700 flex items-center gap-1"
        @click.stop="$emit('drilldown')"
      >
        <UIcon name="i-lucide-arrow-right" class="w-3 h-3" />
        {{ $t('common.viewDetails') }}
      </button>
    </div>
  </div>
</template>
