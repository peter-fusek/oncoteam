<script setup lang="ts">
const { user, clear } = useUserSession()
const { showTestData } = useTestDataToggle()
const { t, locale } = useI18n()
const { setLocale } = useI18n()
const { activeRole, roles, hasMultipleRoles, canAccess, landingPage } = useUserRole()
const { activePatientId, activePatient, patients, hasMultiplePatients, canSwitchPatient, switchPatient } = useActivePatient()
const { isOncology } = usePatientType()

// Pages only shown for oncology patients
const ONCOLOGY_ONLY_PAGES = new Set(['/protocol', '/toxicity', '/prep', '/treatment-map'])

const mobileMenuOpen = ref(false)
const patientSwitcherOpen = ref(false)
const route = useRoute()
const drilldown = useDrilldown()

// Version info from API
const { fetchApi } = useOncoteamApi()
const { data: versionInfo } = fetchApi<{ version: string; commit: string }>('/status', { lazy: true })

// Close mobile menu and drilldown on navigation
watch(() => route.path, () => {
  mobileMenuOpen.value = false
  drilldown.close()
})

const ROLE_COLORS: Record<string, string> = {
  advocate: 'bg-teal-50 text-teal-700 border-teal-200',
  patient: 'bg-blue-50 text-blue-700 border-blue-200',
  doctor: 'bg-purple-50 text-purple-700 border-purple-200',
}

const ROLE_DOTS: Record<string, string> = {
  advocate: 'bg-teal-500',
  patient: 'bg-blue-500',
  doctor: 'bg-purple-500',
}

interface NavSection {
  label: string
  items: Array<{ label: string; icon: string; to: string }>
}

const navigationSections = computed<NavSection[]>(() => {
  const sections: NavSection[] = [
    {
      label: t('nav.sections.overview'),
      items: [
        { label: t('nav.home'), icon: 'i-lucide-layout-dashboard', to: '/' },
        { label: t('nav.patient'), icon: 'i-lucide-user-round', to: '/patient' },
        { label: t('nav.timeline'), icon: 'i-lucide-calendar-clock', to: '/timeline' },
      ],
    },
    {
      label: t('nav.sections.treatment'),
      items: [
        { label: t('nav.labs'), icon: 'i-lucide-test-tube-diagonal', to: '/labs' },
        { label: t('nav.treatmentMap'), icon: 'i-lucide-gantt-chart', to: '/treatment-map' },
        { label: t('nav.imaging'), icon: 'i-lucide-scan-line', to: '/imaging' },
        { label: t('nav.toxicity'), icon: 'i-lucide-thermometer', to: '/toxicity' },
        { label: t('nav.medications'), icon: 'i-lucide-pill', to: '/medications' },
        { label: t('nav.protocol'), icon: 'i-lucide-clipboard-check', to: '/protocol' },
        { label: t('nav.prep'), icon: 'i-lucide-file-check', to: '/prep' },
      ],
    },
    {
      label: t('nav.sections.intelligence'),
      items: [
        { label: t('nav.briefings'), icon: 'i-lucide-bot', to: '/briefings' },
        { label: t('nav.research'), icon: 'i-lucide-microscope', to: '/research' },
        { label: t('nav.familyUpdate'), icon: 'i-lucide-heart-handshake', to: '/family-update' },
        { label: t('nav.dictionary'), icon: 'i-lucide-book-open', to: '/dictionary' },
      ],
    },
    {
      label: t('nav.sections.records'),
      items: [
        { label: t('nav.facts'), icon: 'i-lucide-layers', to: '/facts' },
        { label: t('nav.documents'), icon: 'i-lucide-file-scan', to: '/documents' },
        { label: t('nav.export'), icon: 'i-lucide-package-open', to: '/export' },
      ],
    },
    {
      label: t('nav.sections.operations'),
      items: [
        { label: t('nav.agents'), icon: 'i-lucide-brain-circuit', to: '/agents' },
        { label: t('nav.whatsappHistory'), icon: 'i-lucide-message-circle', to: '/whatsapp-history' },
        { label: t('nav.sessions'), icon: 'i-lucide-messages-square', to: '/sessions' },
        { label: t('nav.oncofiles'), icon: 'i-lucide-database', to: '/oncofiles' },
      ],
    },
  ]

  return sections
    .map(s => ({
      ...s,
      // Rename "Treatment" to "Health" for general health patients
      label: s.label === t('nav.sections.treatment') && !isOncology.value ? t('nav.sections.health') : s.label,
      items: s.items
        .filter(item => canAccess(item.to))
        .filter(item => isOncology.value || !ONCOLOGY_ONLY_PAGES.has(item.to)),
    }))
    .filter(s => s.items.length > 0)
})

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
  <div class="flex h-screen bg-[var(--clinical-bg)]">
    <!-- Desktop sidebar -->
    <aside class="hidden md:flex flex-col w-52 shrink-0 border-r border-gray-200 bg-[var(--clinical-sidebar)]">
      <!-- Header -->
      <div class="flex items-center gap-2.5 px-4 py-3.5">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-600 to-cyan-700 flex items-center justify-center shadow-sm">
          <span class="text-sm text-white">+</span>
        </div>
        <span class="font-bold text-lg text-gray-900 tracking-tight">Oncoteam</span>
      </div>

      <!-- Patient switcher (advocate with multiple patients) -->
      <div v-if="canSwitchPatient && hasMultiplePatients" class="px-3 pb-2">
        <div ref="patientSwitcherRef" class="relative">
          <button
            class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-700 transition-colors hover:border-gray-300"
            @click="patientSwitcherOpen = !patientSwitcherOpen"
          >
            <span class="truncate">{{ activePatient?.name || 'Patient' }}</span>
            <UIcon name="i-lucide-chevrons-up-down" class="w-3 h-3 opacity-50 shrink-0" />
          </button>
          <div
            v-if="patientSwitcherOpen"
            class="absolute top-full left-0 right-0 mt-1 rounded-lg border border-gray-200 bg-white shadow-lg z-10 overflow-hidden"
          >
            <button
              v-for="p in patients"
              :key="p.id"
              class="w-full flex flex-col items-start px-2.5 py-1.5 text-xs transition-colors hover:bg-gray-50"
              :class="p.id === activePatientId ? 'text-gray-900 font-medium' : 'text-gray-500'"
              @click="switchPatient(p.id); patientSwitcherOpen = false"
            >
              <span>{{ p.name }}</span>
              <span class="text-[10px] opacity-60">{{ p.diagnosis }}</span>
            </button>
          </div>
        </div>
      </div>
      <!-- Single patient label (when only one patient) -->
      <div v-else-if="canSwitchPatient" class="px-3 pb-1">
        <span class="text-[10px] text-gray-400 uppercase tracking-wider">{{ activePatient?.name }}</span>
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
            <UIcon name="i-lucide-chevrons-up-down" class="w-3 h-3 opacity-50" />
          </button>
          <div
            v-if="roleSwitcherOpen"
            class="absolute top-full left-0 right-0 mt-1 rounded-lg border border-gray-200 bg-white shadow-lg z-10 overflow-hidden"
          >
            <button
              v-for="role in roles"
              :key="role"
              class="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs transition-colors hover:bg-gray-50"
              :class="role === activeRole ? 'text-gray-900 font-medium' : 'text-gray-500'"
              @click="switchRole(role)"
            >
              <span
                class="w-2 h-2 rounded-full"
                :class="ROLE_DOTS[role]"
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

      <!-- Navigation (grouped sections) -->
      <nav class="flex-1 overflow-y-auto px-2">
        <template v-for="(section, i) in navigationSections" :key="i">
          <div v-if="section.items.length" class="mt-3 first:mt-0">
            <p class="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              {{ section.label }}
            </p>
            <UNavigationMenu :items="section.items" orientation="vertical" />
          </div>
        </template>
      </nav>

      <!-- Footer -->
      <div class="border-t border-gray-200 px-3 py-2 space-y-2">
        <div class="flex items-center justify-between">
          <label v-if="activeRole === 'advocate'" class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-700">
            <input v-model="showTestData" type="checkbox" class="rounded border-gray-300 bg-white text-teal-600 focus:ring-teal-500/30 w-3.5 h-3.5" />
            {{ $t('common.showTestData') }}
          </label>
          <span v-else />
          <button
            class="px-2 py-0.5 text-[10px] font-medium rounded border border-gray-300 text-gray-500 hover:text-gray-900 hover:border-gray-400 transition-colors"
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
            <span class="text-xs text-gray-600 truncate">{{ user?.name }}</span>
          </div>
          <UButton icon="i-lucide-log-out" variant="ghost" size="xs" color="neutral" :label="$t('nav.signOut')" @click="logout" />
        </div>
        <div v-if="versionInfo" class="text-[10px] text-gray-400 text-center">
          v{{ versionInfo.version }} · {{ versionInfo.commit }}
        </div>
      </div>
    </aside>

    <!-- Mobile header -->
    <div class="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-white/95 backdrop-blur-sm">
      <button class="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100" @click="mobileMenuOpen = true">
        <UIcon name="i-lucide-menu" class="w-5 h-5" />
      </button>
      <div class="w-6 h-6 rounded-lg bg-gradient-to-br from-teal-600 to-cyan-700 flex items-center justify-center">
        <span class="text-xs text-white">+</span>
      </div>
      <span class="font-bold text-gray-900">Oncoteam</span>
      <span class="ml-auto inline-flex px-2 py-0.5 rounded border text-[10px] font-medium" :class="ROLE_COLORS[activeRole]">
        {{ $t(`roles.${activeRole}`) }}
      </span>
    </div>

    <!-- Mobile drawer overlay -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="mobileMenuOpen" class="md:hidden fixed inset-0 z-50 bg-black/20" @click="mobileMenuOpen = false" />
      </Transition>
      <Transition name="slide">
        <aside v-if="mobileMenuOpen" class="md:hidden fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-[var(--clinical-sidebar)] border-r border-gray-200 shadow-xl">
          <!-- Header -->
          <div class="flex items-center justify-between px-4 py-3">
            <div class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-600 to-cyan-700 flex items-center justify-center">
                <span class="text-sm text-white">+</span>
              </div>
              <span class="font-bold text-lg text-gray-900">Oncoteam</span>
            </div>
            <button class="p-1 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100" @click="mobileMenuOpen = false">
              <UIcon name="i-lucide-x" class="w-5 h-5" />
            </button>
          </div>

          <!-- Patient switcher (mobile) -->
          <div v-if="canSwitchPatient && hasMultiplePatients" class="px-3 pb-2">
            <select
              class="w-full px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-700"
              :value="activePatientId"
              @change="switchPatient(($event.target as HTMLSelectElement).value)"
            >
              <option v-for="p in patients" :key="p.id" :value="p.id">
                {{ p.name }} — {{ p.diagnosis }}
              </option>
            </select>
          </div>

          <!-- Role switcher (mobile) -->
          <div v-if="hasMultipleRoles" class="px-3 pb-2">
            <div class="flex gap-1">
              <button
                v-for="role in roles"
                :key="role"
                class="flex-1 px-2 py-1.5 rounded-lg border text-xs font-medium transition-colors"
                :class="role === activeRole ? ROLE_COLORS[role] : 'border-gray-200 text-gray-500 hover:text-gray-700'"
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

          <!-- Navigation (grouped sections) -->
          <nav class="flex-1 overflow-y-auto px-2">
            <template v-for="(section, i) in navigationSections" :key="i">
              <div v-if="section.items.length" class="mt-3 first:mt-0">
                <p class="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  {{ section.label }}
                </p>
                <UNavigationMenu :items="section.items" orientation="vertical" />
              </div>
            </template>
          </nav>

          <!-- Footer -->
          <div class="border-t border-gray-200 px-3 py-2 space-y-2">
            <div class="flex items-center justify-between">
              <label v-if="activeRole === 'advocate'" class="flex items-center gap-2 cursor-pointer text-xs text-gray-500 hover:text-gray-700">
                <input v-model="showTestData" type="checkbox" class="rounded border-gray-300 bg-white text-teal-600 focus:ring-teal-500/30 w-3.5 h-3.5" />
                {{ $t('common.showTestData') }}
              </label>
              <span v-else />
              <button
                class="px-2 py-0.5 text-[10px] font-medium rounded border border-gray-300 text-gray-500 hover:text-gray-900 hover:border-gray-400 transition-colors"
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
                <span class="text-xs text-gray-600 truncate">{{ user?.name }}</span>
              </div>
              <UButton icon="i-lucide-log-out" variant="ghost" size="xs" color="neutral" :label="$t('nav.signOut')" @click="logout" />
            </div>
            <div v-if="versionInfo" class="text-[10px] text-gray-400 text-center">
              v{{ versionInfo.version }} · {{ versionInfo.commit }}
            </div>
          </div>
        </aside>
      </Transition>
    </Teleport>

    <!-- Main content -->
    <main class="flex-1 overflow-auto p-4 md:p-6 pt-14 md:pt-6">
      <slot />
      <DrilldownPanel />
      <BugReportButton />
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

/* Sidebar navigation polish — light theme */
aside :deep(.relative a[aria-current="page"]) {
  background: var(--clinical-sidebar-active) !important;
  box-shadow: inset 3px 0 0 var(--clinical-primary);
  color: var(--clinical-primary);
  font-weight: 600;
}

aside :deep(.relative a) {
  transition: all 0.15s ease;
  border-radius: 8px;
  margin: 1px 0;
  color: #4B5563;
}

aside :deep(.relative a:hover) {
  background: var(--clinical-sidebar-hover);
  color: #111827;
}
</style>
