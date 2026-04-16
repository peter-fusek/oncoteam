<script setup lang="ts">
defineProps<{
  icon?: string
  message: string
  offline?: boolean
}>()
</script>

<template>
  <div class="text-center py-16">
    <UIcon
      :name="offline ? 'i-lucide-wifi-off' : (icon || 'i-lucide-inbox')"
      :class="offline ? 'h-6 w-6 mx-auto text-gray-300 mb-2' : 'h-8 w-8 mx-auto text-gray-300 mb-3'"
    />
    <p class="text-sm text-gray-400">{{ message }}</p>
  </div>
</template>
