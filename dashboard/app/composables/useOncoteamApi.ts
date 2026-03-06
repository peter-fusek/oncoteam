export function useOncoteamApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.oncoteamApiUrl
  const { showTestData } = useTestDataToggle()

  function apiUrl(path: string) {
    const sep = path.includes('?') ? '&' : '?'
    const testParam = showTestData.value ? `${sep}show_test=true` : ''
    return `${baseUrl}/api${path}${testParam}`
  }

  function fetchApi<T>(path: string, opts?: Record<string, unknown>) {
    return useFetch<T>(apiUrl(path), {
      ...opts,
    })
  }

  return { apiUrl, fetchApi }
}
