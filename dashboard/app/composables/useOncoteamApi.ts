export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const query = computed(() => {
      const q: Record<string, string> = { lang: locale.value }
      if (showTestData.value) q.show_test = 'true'
      return q
    })

    const url = computed(() => {
      const p = typeof path === 'function' ? path() : unref(path)
      return `/api/oncoteam${p}`
    })

    return useFetch<T>(url, {
      query,
      timeout: 12000,
      ...opts,
    })
  }

  return { fetchApi }
}
