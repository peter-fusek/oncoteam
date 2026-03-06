<script setup lang="ts">
const navigation = [
  { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/' },
  { label: 'Research', icon: 'i-lucide-microscope', to: '/research' },
  { label: 'Timeline', icon: 'i-lucide-calendar-clock', to: '/timeline' },
  { label: 'Sessions', icon: 'i-lucide-messages-square', to: '/sessions' },
]
</script>

<template>
  <div class="flex h-screen">
    <UDashboardSidebar>
      <template #header>
        <div class="flex items-center gap-2 px-2">
          <UIcon name="i-lucide-brain-circuit" class="size-6 text-primary" />
          <span class="font-bold text-lg">Oncoteam</span>
        </div>
      </template>

      <UNavigationMenu :items="navigation" orientation="vertical" />

      <template #footer>
        <div class="px-4 py-2 text-xs text-muted">
          v0.6.1
        </div>
      </template>
    </UDashboardSidebar>

    <main class="flex-1 overflow-auto p-6">
      <slot />
    </main>
  </div>
</template>
