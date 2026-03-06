export function useOncoteamApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.oncoteamApiUrl

  function apiUrl(path: string) {
    return `${baseUrl}/api${path}`
  }

  function fetchApi<T>(path: string, opts?: Record<string, unknown>) {
    return useFetch<T>(apiUrl(path), {
      ...opts,
    })
  }

  return { apiUrl, fetchApi }
}
