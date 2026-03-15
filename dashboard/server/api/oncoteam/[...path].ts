/**
 * Catch-all proxy: forwards /api/oncoteam/<path> to the Python backend.
 * Auth is server-side only — no secrets reach the browser.
 */
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const path = getRouterParam(event, 'path') || ''
  const query = getQuery(event)

  const backendUrl = `${config.oncoteamApiUrl}/api/${path}`
  const qs = new URLSearchParams(query as Record<string, string>).toString()
  const url = qs ? `${backendUrl}?${qs}` : backendUrl

  const headers: Record<string, string> = {}
  if (config.oncoteamApiKey) {
    headers['Authorization'] = `Bearer ${config.oncoteamApiKey}`
  }

  const method = event.method
  const fetchOpts: RequestInit = { method, headers, signal: AbortSignal.timeout(12_000) }

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
    setResponseStatus(event, 502)
    return { error: message, data: [] }
  }
})
