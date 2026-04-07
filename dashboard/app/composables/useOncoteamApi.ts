export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()
  const { activePatientId } = useActivePatient()

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const resolvedPath = typeof path === 'function' ? path() : unref(path)
    const pid = activePatientId.value || 'erika'

    // Key must be a plain string — evaluated once at setup with current patient
    const key = `oncoteam:${pid}:${resolvedPath}`

    const query = computed(() => {
      const q: Record<string, string> = { lang: locale.value }
      if (showTestData.value) q.show_test = 'true'
      if (activePatientId.value) q.patient_id = activePatientId.value
      return q
    })

    return useFetch<T>(`/api/oncoteam${resolvedPath}`, {
      key,
      query,
      timeout: 28000,
      server: false,
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
