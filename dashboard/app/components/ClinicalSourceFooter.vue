<script setup lang="ts">
// Footer for any clinical value that the UI displays: shows the guideline /
// paper / document it came from plus the informational-only disclaimer.
// Mounted on labs charts, biomarker cards, protocol tables, briefings, and
// family updates so the advocate can defend every number to their oncologist.
// See memory/feedback_medical-traceability.md — every clinical fact MUST
// cite a source + render the "physician verifies" framing.

interface Source {
  label: string
  url?: string
}

const props = defineProps<{
  sources?: Source[]
  documentUrl?: string | null
  documentLabel?: string
  compact?: boolean
}>()

const hasAnySource = computed(
  () => (props.sources && props.sources.length > 0) || !!props.documentUrl,
)
</script>

<template>
  <div
    class="border-t border-gray-100 pt-2 mt-3 text-[11px] leading-snug text-gray-500 flex flex-wrap items-start gap-x-3 gap-y-1"
    :class="compact ? 'text-[10px]' : ''"
  >
    <span class="inline-flex items-center gap-1 italic">
      <UIcon name="i-lucide-shield-check" class="w-3 h-3 text-gray-400 shrink-0" />
      {{ $t('components.clinicalSource.disclaimer') }}
    </span>

    <template v-if="hasAnySource">
      <span class="text-gray-300">·</span>
      <span class="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span class="text-gray-400">{{ $t('components.clinicalSource.source') }}:</span>
        <template v-for="(s, i) in sources || []" :key="i">
          <span v-if="i > 0" class="text-gray-300">·</span>
          <a
            v-if="s.url"
            :href="s.url"
            target="_blank"
            rel="noreferrer"
            class="underline decoration-dotted decoration-gray-400 hover:decoration-green-600 hover:text-green-700 transition-colors"
          >{{ s.label }}</a>
          <span v-else>{{ s.label }}</span>
        </template>
        <template v-if="documentUrl">
          <span v-if="sources?.length" class="text-gray-300">·</span>
          <a
            :href="documentUrl"
            target="_blank"
            rel="noreferrer"
            class="inline-flex items-center gap-1 underline decoration-dotted decoration-gray-400 hover:decoration-green-600 hover:text-green-700 transition-colors"
          >
            <UIcon name="i-lucide-file-text" class="w-3 h-3" />
            {{ documentLabel || $t('components.clinicalSource.sourceDocument') }}
          </a>
        </template>
      </span>
    </template>
  </div>
</template>
