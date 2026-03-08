<template>
  <div
    v-if="error"
    class="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400 flex items-center gap-2"
  >
    <UIcon name="i-lucide-alert-triangle" class="shrink-0" />
    <span>{{ $t('components.apiError') }}: {{ error }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ error?: string | null }>()
</script>
