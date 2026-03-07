<script setup lang="ts">
const { user, clear } = useUserSession()
const { showTestData } = useTestDataToggle()

const navigation = [
  { label: 'Agents', icon: 'i-lucide-brain-circuit', to: '/' },
  { label: 'Patient', icon: 'i-lucide-user-round', to: '/patient' },
  { label: 'Protocol', icon: 'i-lucide-clipboard-check', to: '/protocol' },
  { label: 'Toxicity', icon: 'i-lucide-thermometer', to: '/toxicity' },
  { label: 'Labs', icon: 'i-lucide-test-tube-diagonal', to: '/labs' },
  { label: 'Briefings', icon: 'i-lucide-bot', to: '/briefings' },
  { label: 'Prep', icon: 'i-lucide-file-check', to: '/prep' },
  { label: 'Research', icon: 'i-lucide-microscope', to: '/research' },
  { label: 'Timeline', icon: 'i-lucide-calendar-clock', to: '/timeline' },
  { label: 'Sessions', icon: 'i-lucide-messages-square', to: '/sessions' },
]

async function logout() {
  await $fetch('/auth/logout', { method: 'POST' })
  clear()
  navigateTo('/login')
}
</script>

<template>
  <div class="flex h-screen bg-gray-950">
    <UDashboardSidebar class="border-r border-gray-800">
      <template #header>
        <div class="flex items-center gap-2 px-2">
          <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center">
            <span class="text-sm">🧬</span>
          </div>
          <span class="font-bold text-lg text-white">Oncoteam</span>
        </div>
      </template>

      <UNavigationMenu :items="navigation" orientation="vertical" />

      <template #footer>
        <div class="px-3 py-2 space-y-2">
          <label class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-400">
            <input v-model="showTestData" type="checkbox" class="rounded border-gray-700 bg-gray-800 text-amber-500 focus:ring-amber-500/30 w-3.5 h-3.5" />
            Show test data
          </label>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 min-w-0">
              <UAvatar
                v-if="user?.picture"
                :src="user.picture"
                size="xs"
              />
              <span class="text-xs text-gray-400 truncate">{{ user?.name }}</span>
            </div>
            <UButton icon="i-lucide-log-out" variant="ghost" size="xs" color="neutral" @click="logout" />
          </div>
        </div>
      </template>
    </UDashboardSidebar>

    <main class="flex-1 overflow-auto p-6">
      <slot />
    </main>
  </div>
</template>
