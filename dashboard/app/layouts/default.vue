<script setup lang="ts">
const { user, clear } = useUserSession()
const { showTestData } = useTestDataToggle()
const { t, locale } = useI18n()
const { setLocale } = useI18n()
const { activeRole, roles, hasMultipleRoles, canAccess, landingPage } = useUserRole()

const mobileMenuOpen = ref(false)
const route = useRoute()

// Close mobile menu on navigation
watch(() => route.path, () => {
  mobileMenuOpen.value = false
})

const ROLE_COLORS: Record<string, string> = {
  advocate: 'bg-teal-500/20 text-teal-400 border-teal-500/30',
  patient: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  doctor: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
}

const allNavItems = computed(() => [
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

const navigation = computed(() => allNavItems.value.filter(item => canAccess(item.to)))

const roleSwitcherOpen = ref(false)
const roleSwitcherRef = ref<HTMLElement | null>(null)

// Click-outside handler for role switcher dropdown
function onClickOutside(e: MouseEvent) {
  if (roleSwitcherOpen.value && roleSwitcherRef.value && !roleSwitcherRef.value.contains(e.target as Node)) {
    roleSwitcherOpen.value = false
  }
}
onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))

async function switchRole(role: string) {
  roleSwitcherOpen.value = false
  await $fetch('/api/role/switch', { method: 'POST', body: { role } })
  await navigateTo(landingPage.value, { external: true })
}

async function toggleLocale() {
  await setLocale(locale.value === 'sk' ? 'en' : 'sk')
}

async function logout() {
  await $fetch('/auth/logout', { method: 'POST' })
  clear()
  navigateTo('/login')
}
</script>

<template>
  <div class="flex h-screen bg-gray-950">
    <!-- Desktop sidebar -->
    <aside class="hidden md:flex flex-col w-52 shrink-0 border-r border-gray-800 bg-gray-950">
      <!-- Header -->
      <div class="flex items-center gap-2 px-4 py-3">
        <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center">
          <span class="text-sm">🧬</span>
        </div>
        <span class="font-bold text-lg text-white">Oncoteam</span>
      </div>

      <!-- Role switcher -->
      <div v-if="hasMultipleRoles" class="px-3 pb-2">
        <div ref="roleSwitcherRef" class="relative">
          <button
            class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors"
            :class="ROLE_COLORS[activeRole]"
            @click="roleSwitcherOpen = !roleSwitcherOpen"
          >
            <span>{{ $t(`roles.${activeRole}`) }}</span>
            <UIcon name="i-lucide-chevrons-up-down" class="w-3 h-3 opacity-60" />
          </button>
          <div
            v-if="roleSwitcherOpen"
            class="absolute top-full left-0 right-0 mt-1 rounded-lg border border-gray-700 bg-gray-900 shadow-xl z-10 overflow-hidden"
          >
            <button
              v-for="role in roles"
              :key="role"
              class="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs transition-colors hover:bg-gray-800"
              :class="role === activeRole ? 'text-white font-medium' : 'text-gray-400'"
              @click="switchRole(role)"
            >
              <span
                class="w-2 h-2 rounded-full"
                :class="{
                  'bg-teal-500': role === 'advocate',
                  'bg-blue-500': role === 'patient',
                  'bg-purple-500': role === 'doctor',
                }"
              />
              {{ $t(`roles.${role}`) }}
            </button>
          </div>
        </div>
      </div>

      <!-- Single role badge -->
      <div v-else class="px-3 pb-2">
        <span class="inline-flex px-2.5 py-1 rounded-lg border text-xs font-medium" :class="ROLE_COLORS[activeRole]">
          {{ $t(`roles.${activeRole}`) }}
        </span>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 overflow-y-auto px-2">
        <UNavigationMenu :items="navigation" orientation="vertical" />
      </nav>

      <!-- Footer -->
      <div class="border-t border-gray-800 px-3 py-2 space-y-2">
        <div class="flex items-center justify-between">
          <label v-if="activeRole === 'advocate'" class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-400">
            <input v-model="showTestData" type="checkbox" class="rounded border-gray-700 bg-gray-800 text-amber-500 focus:ring-amber-500/30 w-3.5 h-3.5" />
            {{ $t('common.showTestData') }}
          </label>
          <span v-else />
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
    </aside>

    <!-- Mobile header -->
    <div class="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center gap-2 px-3 py-2 border-b border-gray-800 bg-gray-950">
      <button class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800" @click="mobileMenuOpen = true">
        <UIcon name="i-lucide-menu" class="w-5 h-5" />
      </button>
      <div class="w-6 h-6 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center">
        <span class="text-xs">🧬</span>
      </div>
      <span class="font-bold text-white">Oncoteam</span>
      <span class="ml-auto inline-flex px-2 py-0.5 rounded border text-[10px] font-medium" :class="ROLE_COLORS[activeRole]">
        {{ $t(`roles.${activeRole}`) }}
      </span>
    </div>

    <!-- Mobile drawer overlay -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="mobileMenuOpen" class="md:hidden fixed inset-0 z-50 bg-black/60" @click="mobileMenuOpen = false" />
      </Transition>
      <Transition name="slide">
        <aside v-if="mobileMenuOpen" class="md:hidden fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-gray-950 border-r border-gray-800 shadow-xl">
          <!-- Header -->
          <div class="flex items-center justify-between px-4 py-3">
            <div class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center">
                <span class="text-sm">🧬</span>
              </div>
              <span class="font-bold text-lg text-white">Oncoteam</span>
            </div>
            <button class="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800" @click="mobileMenuOpen = false">
              <UIcon name="i-lucide-x" class="w-5 h-5" />
            </button>
          </div>

          <!-- Role switcher (mobile) -->
          <div v-if="hasMultipleRoles" class="px-3 pb-2">
            <div class="flex gap-1">
              <button
                v-for="role in roles"
                :key="role"
                class="flex-1 px-2 py-1.5 rounded-lg border text-xs font-medium transition-colors"
                :class="role === activeRole ? ROLE_COLORS[role] : 'border-gray-700 text-gray-500 hover:text-gray-300'"
                @click="switchRole(role)"
              >
                {{ $t(`roles.${role}`) }}
              </button>
            </div>
          </div>
          <div v-else class="px-3 pb-2">
            <span class="inline-flex px-2.5 py-1 rounded-lg border text-xs font-medium" :class="ROLE_COLORS[activeRole]">
              {{ $t(`roles.${activeRole}`) }}
            </span>
          </div>

          <!-- Navigation -->
          <nav class="flex-1 overflow-y-auto px-2">
            <UNavigationMenu :items="navigation" orientation="vertical" />
          </nav>

          <!-- Footer -->
          <div class="border-t border-gray-800 px-3 py-2 space-y-2">
            <div class="flex items-center justify-between">
              <label v-if="activeRole === 'advocate'" class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-400">
                <input v-model="showTestData" type="checkbox" class="rounded border-gray-700 bg-gray-800 text-amber-500 focus:ring-amber-500/30 w-3.5 h-3.5" />
                {{ $t('common.showTestData') }}
              </label>
              <span v-else />
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
        </aside>
      </Transition>
    </Teleport>

    <!-- Main content -->
    <main class="flex-1 overflow-auto p-4 md:p-6 pt-14 md:pt-6">
      <slot />
      <DrilldownPanel />
    </main>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}
</style>
