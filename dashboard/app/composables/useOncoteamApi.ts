export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()
  const { activePatientId } = useActivePatient()

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const resolvedPath = computed(() => typeof path === 'function' ? path() : unref(path))

    const queryParams = computed(() => {
      const q: Record<string, string> = { lang: locale.value }
      if (showTestData.value) q.show_test = 'true'
      if (activePatientId.value) q.patient_id = activePatientId.value
      return q
    })

    // Explicit cache key includes patient_id so switching patients fetches fresh data
    const cacheKey = computed(() => `oncoteam:${activePatientId.value}:${resolvedPath.value}`)

    return useAsyncData<T>(
      cacheKey,
      () => $fetch<T>(`/api/oncoteam${resolvedPath.value}`, {
        params: queryParams.value,
        timeout: 28000,
      }),
      {
        server: false,
        watch: [activePatientId as Ref<string>, locale],
        ...opts,
      },
    )
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
