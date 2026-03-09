export function useOncoteamApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.oncoteamApiUrl
  const { showTestData } = useTestDataToggle()
  const { locale } = useI18n()

  function apiUrl(path: string) {
    const url = `${baseUrl}/api${path}`
    const sep = url.includes('?') ? '&' : '?'
    const params: string[] = []
    params.push(`lang=${locale.value}`)
    if (showTestData.value) params.push('show_test=true')
    return `${url}${sep}${params.join('&')}`
  }

  function fetchApi<T>(path: string, opts?: Record<string, unknown>) {
    return useFetch<T>(apiUrl(path), {
      ...opts,
    })
  }

  return { apiUrl, fetchApi }
}
