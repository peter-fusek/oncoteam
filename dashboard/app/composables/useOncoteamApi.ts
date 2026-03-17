export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()

  function fetchApi<T>(path: string | Ref<string> | (() => string), opts?: Record<string, unknown>) {
    const query: Record<string, string> = { lang: locale.value }
    if (showTestData.value) query.show_test = 'true'

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
