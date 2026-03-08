<script setup lang="ts">
const { user, clear } = useUserSession()
const { showTestData } = useTestDataToggle()
const { t, locale, locales } = useI18n()

const navigation = computed(() => [
  { label: t('nav.agents'), icon: 'i-lucide-brain-circuit', to: '/' },
  { label: t('nav.patient'), icon: 'i-lucide-user-round', to: '/patient' },
  { label: t('nav.protocol'), icon: 'i-lucide-clipboard-check', to: '/protocol' },
  { label: t('nav.toxicity'), icon: 'i-lucide-thermometer', to: '/toxicity' },
  { label: t('nav.medications'), icon: 'i-lucide-pill', to: '/medications' },
  { label: t('nav.labs'), icon: 'i-lucide-test-tube-diagonal', to: '/labs' },
  { label: t('nav.briefings'), icon: 'i-lucide-bot', to: '/briefings' },
  { label: t('nav.prep'), icon: 'i-lucide-file-check', to: '/prep' },
  { label: t('nav.research'), icon: 'i-lucide-microscope', to: '/research' },
  { label: t('nav.timeline'), icon: 'i-lucide-calendar-clock', to: '/timeline' },
  { label: t('nav.sessions'), icon: 'i-lucide-messages-square', to: '/sessions' },
  { label: t('nav.familyUpdate'), icon: 'i-lucide-heart-handshake', to: '/family-update' },
])

function toggleLocale() {
  locale.value = locale.value === 'sk' ? 'en' : 'sk'
}

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
          <div class="flex items-center justify-between">
            <label class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-400">
              <input v-model="showTestData" type="checkbox" class="rounded border-gray-700 bg-gray-800 text-amber-500 focus:ring-amber-500/30 w-3.5 h-3.5" />
              {{ $t('common.showTestData') }}
            </label>
            <button
              class="px-2 py-0.5 text-[10px] font-medium rounded border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
              @click="toggleLocale"
            >
              {{ locale === 'sk' ? 'EN' : 'SK' }}
            </button>
          </div>
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
      <DrilldownPanel />
    </main>
  </div>
</template>
