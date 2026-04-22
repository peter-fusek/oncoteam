/**
 * Proxy to oncofiles /readiness — the authoritative source for the
 * breaker banner after oncofiles#469 / oncoteam#424.
 *
 * Fetched server-side to sidestep CORS + avoid requiring the client to
 * know the oncofiles host. No auth required on the upstream endpoint —
 * /readiness is documented as public telemetry. Still session-gated here
 * so only authenticated dashboard users can observe state.
 *
 * The response preserves oncofiles' circuit_breaker shape verbatim so
 * the composable maps it 1:1 without any heuristic inference.
 */
export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }

  const config = useRuntimeConfig()
  const url = (config as unknown as { oncofilesReadinessUrl: string }).oncofilesReadinessUrl

  try {
    const resp = await fetch(url, {
      method: 'GET',
      headers: { 'cache-control': 'no-store' },
      signal: AbortSignal.timeout(5_000),
    })
    if (!resp.ok) {
      setResponseStatus(event, resp.status)
      return { error: `upstream ${resp.status}`, circuit_breaker: null }
    }
    const data = await resp.json()
    return data
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'readiness fetch failed'
    console.error(`[oncofiles-readiness] ${url} failed: ${message}`)
    setResponseStatus(event, 502)
    return { error: message, circuit_breaker: null }
  }
})
