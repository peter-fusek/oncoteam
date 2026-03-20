<template>
  <div class="animate-pulse space-y-4">
    <!-- stat-grid: 4 stat cards -->
    <template v-if="variant === 'stat-grid'">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div v-for="i in 4" :key="i" class="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
          <div class="h-3 w-16 bg-gray-100 rounded" />
          <div class="h-6 w-24 bg-gray-100 rounded" />
          <div class="h-2 w-12 bg-gray-50 rounded" />
        </div>
      </div>
    </template>

    <!-- card: single content card -->
    <template v-else-if="variant === 'card'">
      <div class="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
        <div class="h-4 w-48 bg-gray-100 rounded" />
        <div class="h-3 w-full bg-gray-100 rounded" />
        <div class="h-3 w-3/4 bg-gray-100 rounded" />
        <div class="h-3 w-5/6 bg-gray-100 rounded" />
      </div>
    </template>

    <!-- table: header + rows -->
    <template v-else-if="variant === 'table'">
      <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200">
          <div class="h-4 w-32 bg-gray-100 rounded" />
        </div>
        <div class="divide-y divide-gray-100">
          <div v-for="i in (rows || 5)" :key="i" class="px-4 py-3 flex items-center gap-4">
            <div class="h-3 w-20 bg-gray-100 rounded" />
            <div class="h-3 w-32 bg-gray-100 rounded" />
            <div class="h-3 w-16 bg-gray-50 rounded ml-auto" />
          </div>
        </div>
      </div>
    </template>

    <!-- cards: multiple cards -->
    <template v-else-if="variant === 'cards'">
      <div class="space-y-3">
        <div v-for="i in (rows || 3)" :key="i" class="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
          <div class="flex items-center justify-between">
            <div class="h-4 w-40 bg-gray-100 rounded" />
            <div class="h-3 w-16 bg-gray-50 rounded" />
          </div>
          <div class="h-3 w-full bg-gray-100 rounded" />
          <div class="h-3 w-2/3 bg-gray-100 rounded" />
        </div>
      </div>
    </template>

    <!-- text: simple text lines (default) -->
    <template v-else>
      <div class="space-y-3">
        <div class="h-4 w-48 bg-gray-100 rounded" />
        <div class="h-3 w-full bg-gray-100 rounded" />
        <div class="h-3 w-5/6 bg-gray-100 rounded" />
        <div class="h-3 w-3/4 bg-gray-100 rounded" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  variant?: 'card' | 'table' | 'text' | 'stat-grid' | 'cards'
  rows?: number
}>()
</script>
