export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()
  const { activePatientId } = useActivePatient()

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const query = computed(() => {
      const q: Record<string, string> = { lang: locale.value }
      if (showTestData.value) q.show_test = 'true'
      if (activePatientId.value) q.patient_id = activePatientId.value
      return q
    })

    const url = computed(() => {
      const p = typeof path === 'function' ? path() : unref(path)
      return `/api/oncoteam${p}`
    })

    return useFetch<T>(url, {
      query,
      timeout: 28000, // Must exceed server proxy timeout (25s) to avoid premature client abort
      server: false, // Client-only — SSR data fetches caused 503s (Railway edge 17s timeout)
      ...opts,
    })
  }

  async function postApi<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const q: Record<string, string> = { lang: locale.value }
    if (showTestData.value) q.show_test = 'true'
    if (activePatientId.value) q.patient_id = activePatientId.value
    const qs = new URLSearchParams(q).toString()
    return $fetch<T>(`/api/oncoteam${path}?${qs}`, { method: 'POST', body })
  }

  return { fetchApi, postApi }
}
