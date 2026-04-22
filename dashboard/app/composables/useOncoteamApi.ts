import { apiFetch, parseRetryAfter, type ApiFetchError } from './useApiFetch'
import { isSwrPath, swrGet, swrSet, swrClearAll, swrClearPatient } from './useSwrCache'

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

    // Retry-After surfaced for the active fetch — callers (banner) read this
    // to size the countdown. Null/0 when the last fetch succeeded.
    const retryAfterMs = ref<number>(0)
    // SWR: true when the data ref is populated from sessionStorage cache
    // because the live fetch failed. ageMs is the cache age in ms.
    const stale = ref<boolean>(false)
    const cacheAgeMs = ref<number>(0)

    async function doFetch(): Promise<T> {
      const qs = new URLSearchParams(query.value).toString()
      const url = `/api/oncoteam${resolvedPath}${qs ? `?${qs}` : ''}`
      try {
        const data = await apiFetch<T>(url, { perRequestTimeoutMs: 28000 })
        retryAfterMs.value = 0
        stale.value = false
        cacheAgeMs.value = 0
        if (isSwrPath(resolvedPath)) {
          swrSet<T>(effectivePatientId.value, resolvedPath, data)
        }
        return data
      } catch (e) {
        const err = e as ApiFetchError
        if (err?.status === 503 && err.retryAfterMs) {
          retryAfterMs.value = err.retryAfterMs
        }
        // Fall back to cached data for SWR-eligible paths so the UI
        // stays populated instead of collapsing to the empty state.
        if (isSwrPath(resolvedPath)) {
          const hit = swrGet<T>(effectivePatientId.value, resolvedPath)
          if (hit) {
            stale.value = true
            cacheAgeMs.value = hit.ageMs
            return hit.data
          }
        }
        throw err
      }
    }

    const fetched = useAsyncData<T>(key, doFetch, {
      lazy: true,
      server: false,
      watch: [query],
      ...(opts as Record<string, unknown>),
    })

    async function forceRefresh() {
      nocacheTick.value = Date.now()
      await fetched.refresh()
    }

    return { ...fetched, forceRefresh, retryAfterMs, stale, cacheAgeMs }
  }

  async function postApi<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const q: Record<string, string> = { lang: locale.value }
    if (showTestData.value) q.show_test = 'true'
    q.patient_id = effectivePatientId.value
    const qs = new URLSearchParams(q).toString()
    return apiFetch<T>(`/api/oncoteam${path}?${qs}`, { method: 'POST', body })
  }

  return {
    fetchApi,
    postApi,
    parseRetryAfter,
    swrClearAll,
    swrClearPatient,
  }
}
