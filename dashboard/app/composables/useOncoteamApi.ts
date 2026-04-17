export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()
  const { activePatientId } = useActivePatient()

  // Read cookie directly as fallback — activePatientId may not be updated yet during SSR
  // Validate cookie looks like a patient slug (2-10 alphanumeric chars), not a display name
  const patientCookie = useCookie('oncoteam_patient')
  const validCookie = computed(() => {
    const v = patientCookie.value
    return v && /^[a-z0-9]{2,10}$/.test(v) ? v : ''
  })
  const effectivePatientId = computed(() => validCookie.value || activePatientId.value || 'q1b')

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const resolvedPath = typeof path === 'function' ? path() : unref(path)
    const pid = effectivePatientId.value

    const key = `oncoteam:${pid}:${resolvedPath}`
    const nocacheTick = ref(0)

    const query = computed(() => {
      const q: Record<string, string> = { lang: locale.value }
      if (showTestData.value) q.show_test = 'true'
      q.patient_id = effectivePatientId.value
      // Bypass backend TTL cache on forced refresh (#373). The tick also
      // becomes part of the URL so Nuxt's own request dedupe won't drop it.
      if (nocacheTick.value) {
        q.nocache = '1'
        q._t = String(nocacheTick.value)
      }
      return q
    })

    const fetched = useFetch<T>(`/api/oncoteam${resolvedPath}`, {
      key,
      query,
      timeout: 28000,
      server: false,
      retry: 1,
      retryDelay: 2000,
      retryStatusCodes: [502, 503],
      ...opts,
    })

    async function forceRefresh() {
      nocacheTick.value = Date.now()
      await fetched.refresh()
    }

    return { ...fetched, forceRefresh }
  }

  async function postApi<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const q: Record<string, string> = { lang: locale.value }
    if (showTestData.value) q.show_test = 'true'
    q.patient_id = effectivePatientId.value
    const qs = new URLSearchParams(q).toString()
    return $fetch<T>(`/api/oncoteam${path}?${qs}`, { method: 'POST', body })
  }

  return { fetchApi, postApi }
}
