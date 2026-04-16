const PAGE_ACCESS: Record<string, string[]> = {
  '/': ['advocate', 'patient', 'doctor'],
  '/patient': ['advocate', 'patient', 'doctor'],
  '/timeline': ['advocate', 'patient', 'doctor'],
  '/treatment-map': ['advocate', 'doctor'],
  '/protocol': ['advocate', 'doctor'],
  '/labs': ['advocate', 'doctor'],
  '/toxicity': ['advocate', 'patient', 'doctor'],
  '/medications': ['advocate', 'patient'],
  '/prep': ['advocate', 'doctor'],
  '/briefings': ['advocate'],
  '/research': ['advocate', 'doctor'],
  '/family-update': ['advocate', 'patient'],
  '/dictionary': ['advocate', 'patient', 'doctor'],
  '/agents': ['advocate'],
  '/prompts': ['advocate'],
  '/whatsapp-history': ['advocate'],
  '/sessions': ['advocate'],
  '/documents': ['advocate'],
  '/export': ['advocate', 'doctor'],
  '/oncofiles': ['advocate'],
}

const LANDING_PAGES: Record<string, string> = {
  advocate: '/',
  patient: '/',
  doctor: '/',
}

export function useUserRole() {
  const { user } = useUserSession()

  const activeRole = computed(() => user.value?.activeRole || 'advocate')
  const roles = computed(() => [...new Set(user.value?.roles || ['advocate'])])
  const hasMultipleRoles = computed(() => roles.value.length > 1)
  const landingPage = computed(() => LANDING_PAGES[activeRole.value] || '/')

  function canAccess(path: string): boolean {
    // Login page is always accessible
    if (path === '/login') return true
    const allowed = PAGE_ACCESS[path]
    // Deny access to unlisted pages (secure by default)
    if (!allowed) return activeRole.value === 'advocate'
    return allowed.includes(activeRole.value)
  }

  return { activeRole, roles, hasMultipleRoles, landingPage, canAccess, PAGE_ACCESS }
}
