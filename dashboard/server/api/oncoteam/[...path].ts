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

  // Forward session-derived actor identity so backend api_funnel can distinguish
  // physician / advocate / agent actions without trusting the JSON body (#395).
  // Any caller that could impersonate an agent MUST set its own bearer — the
  // proxy only ever declares `human` actors, so agent escalation through the
  // browser is impossible.
  const sessionUser = session.user as {
    email?: string
    name?: string
    roles?: string[]
  } | undefined
  const actorId = sessionUser?.email || sessionUser?.name || 'advocate'
  const actorDisplay = sessionUser?.name || actorId
  headers['X-Actor-Type'] = 'human'
  headers['X-Actor-Id'] = actorId
  headers['X-Actor-Display-Name'] = actorDisplay
  const roles = sessionUser?.roles ?? []
  if (roles.length) headers['X-Actor-Roles'] = roles.join(',')

  const method = event.method
  const fetchOpts: RequestInit = { method, headers, signal: AbortSignal.timeout(25_000) }

  if (method === 'POST') {
    const body = await readBody(event)
    fetchOpts.body = JSON.stringify(body)
    headers['Content-Type'] = 'application/json'
  }

  try {
    const response = await fetch(url, fetchOpts)
    const data = await response.json()
    setResponseStatus(event, response.status)
    return data
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Backend unavailable'
    console.error(`[oncoteam-proxy] ${method} ${url} failed: ${message}`)
    setResponseStatus(event, 502)
    return { error: message, data: [] }
  }
})
