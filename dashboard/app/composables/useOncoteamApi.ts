export function useOncoteamApi() {
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()

  function fetchApi<T>(path: string, opts?: Record<string, unknown>) {
    const query: Record<string, string> = { lang: locale.value }
    if (showTestData.value) query.show_test = 'true'

    return useFetch<T>(`/api/oncoteam${path}`, {
      query,
      timeout: 12000,
      ...opts,
    })
  }

  return { fetchApi }
}
