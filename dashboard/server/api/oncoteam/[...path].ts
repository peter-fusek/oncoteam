/**
 * Catch-all proxy: forwards /api/oncoteam/<path> to the Python backend.
 * Session-gated — requires authenticated user. API key stays server-side.
 */
export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) {
    throw createError({ statusCode: 401, message: 'Not authenticated' })
  }

  // Validate patient_id against user's authorized patients
  const query = getQuery(event)
  const requestedPatientId = query.patient_id as string | undefined
  const allowedPatientIds = (session.user as { patientIds?: string[] }).patientIds || []
  if (requestedPatientId && allowedPatientIds.length > 0 && !allowedPatientIds.includes(requestedPatientId)) {
    throw createError({ statusCode: 403, message: 'Access denied to patient' })
  }

  const config = useRuntimeConfig()
  const path = getRouterParam(event, 'path') || ''

  const backendUrl = `${config.oncoteamApiUrl}/api/${path}`
  const qs = new URLSearchParams(query as Record<string, string>).toString()
  const url = qs ? `${backendUrl}?${qs}` : backendUrl

  const headers: Record<string, string> = {}
  if (config.oncoteamApiKey) {
    headers['Authorization'] = `Bearer ${config.oncoteamApiKey}`
  }

  const method = event.method

  // AbortController + clearTimeout instead of AbortSignal.timeout(): the latter
  // keeps its internal timer alive for the full 25s after the fetch settles,
  // retaining the response object in memory. Under 7-8 parallel page-load calls
  // this accumulates dozens of live timers, blocking GC (#447).
  const ac = new AbortController()
  const tid = setTimeout(() => ac.abort(new DOMException('Upstream timeout', 'TimeoutError')), 25_000)

  const fetchOpts: RequestInit = { method, headers, signal: ac.signal }

  if (method === 'POST') {
    const body = await readBody(event)
    fetchOpts.body = JSON.stringify(body)
    headers['Content-Type'] = 'application/json'
  }

  let response: Response | undefined
  try {
    response = await fetch(url, fetchOpts)
    const data = await response.json()
    setResponseStatus(event, response.status)
    return data
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Backend unavailable'
    console.error(`[oncoteam-proxy] ${method} ${url} failed: ${message}`)
    setResponseStatus(event, 502)
    // 3rd leak vector (#447): undici keeps the response body in memory until
    // it is consumed or cancelled. If response.json() above threw (e.g. backend
    // returned an HTML 502 instead of JSON, or the stream errored mid-read),
    // we have a `response` reference whose body stream is still pinned. Drain
    // it explicitly to release the buffers. .cancel() is fire-and-forget; if
    // it rejects (already-consumed body etc.) we don't care.
    //
    // Credit: @m13v on the #447 thread —
    // https://github.com/peter-fusek/oncoteam/issues/447#issuecomment-4322984724
    // ("undici keeps the response body in memory until you actually consume or
    // cancel it. ... shaved another ~30MB/req that way after the timer fix landed")
    if (response?.body && !response.bodyUsed) {
      response.body.cancel().catch(() => { /* already consumed */ })
    }
    return { error: message, data: [] }
  } finally {
    clearTimeout(tid)
  }
})
