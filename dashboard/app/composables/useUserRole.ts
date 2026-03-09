const PAGE_ACCESS: Record<string, string[]> = {
  '/': ['advocate'],
  '/patient': ['advocate', 'patient', 'doctor'],
  '/protocol': ['advocate', 'doctor'],
  '/toxicity': ['advocate', 'patient', 'doctor'],
  '/medications': ['advocate', 'patient'],
  '/labs': ['advocate', 'doctor'],
  '/briefings': ['advocate'],
  '/prep': ['advocate', 'doctor'],
  '/research': ['advocate', 'doctor'],
  '/timeline': ['advocate', 'patient', 'doctor'],
  '/sessions': ['advocate'],
  '/family-update': ['advocate', 'patient'],
}

const LANDING_PAGES: Record<string, string> = {
  advocate: '/',
  patient: '/patient',
  doctor: '/labs',
}

export function useUserRole() {
  const { user } = useUserSession()

  const activeRole = computed(() => user.value?.activeRole || 'advocate')
  const roles = computed(() => user.value?.roles || ['advocate'])
  const hasMultipleRoles = computed(() => roles.value.length > 1)
  const landingPage = computed(() => LANDING_PAGES[activeRole.value] || '/')

  function canAccess(path: string): boolean {
    const allowed = PAGE_ACCESS[path]
    if (!allowed) return true
    return allowed.includes(activeRole.value)
  }

  return { activeRole, roles, hasMultipleRoles, landingPage, canAccess, PAGE_ACCESS }
}
