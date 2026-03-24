export type FunnelStage = 'Excluded' | 'Later Line' | 'Watching' | 'Eligible Now' | 'Action Needed'

export const FUNNEL_STAGES: FunnelStage[] = ['Excluded', 'Later Line', 'Watching', 'Eligible Now', 'Action Needed']

export interface FunnelAssessment {
  stage: FunnelStage
  exclusion_reason: string | null
  next_step: string
  deadline_note: string | null
  assessed_at: string
  manually_moved?: boolean
}

export function useFunnelStage() {
  const { activePatientId } = useActivePatient()

  function storageKey(nctId: string): string {
    return `funnel::${activePatientId.value || 'default'}::${nctId}`
  }

  function getStage(nctId: string): FunnelAssessment | null {
    if (!import.meta.client) return null
    try {
      const raw = localStorage.getItem(storageKey(nctId))
      return raw ? JSON.parse(raw) : null
    }
    catch { return null }
  }

  function setStage(nctId: string, assessment: FunnelAssessment): void {
    if (!import.meta.client) return
    localStorage.setItem(storageKey(nctId), JSON.stringify(assessment))
  }

  function moveStage(nctId: string, newStage: FunnelStage): void {
    const existing = getStage(nctId)
    setStage(nctId, {
      stage: newStage,
      exclusion_reason: existing?.exclusion_reason ?? null,
      next_step: existing?.next_step ?? 'Manually moved',
      deadline_note: existing?.deadline_note ?? null,
      assessed_at: new Date().toISOString(),
      manually_moved: true,
    })
  }

  function getAllStages(): Record<string, FunnelAssessment> {
    if (!import.meta.client) return {}
    const prefix = `funnel::${activePatientId.value || 'default'}::`
    const result: Record<string, FunnelAssessment> = {}
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) {
        try {
          const nctId = key.slice(prefix.length)
          result[nctId] = JSON.parse(localStorage.getItem(key) || '{}')
        }
        catch { /* skip corrupt entries */ }
      }
    }
    return result
  }

  function clearAll(): void {
    if (!import.meta.client) return
    const prefix = `funnel::${activePatientId.value || 'default'}::`
    const toRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) toRemove.push(key)
    }
    toRemove.forEach(k => localStorage.removeItem(k))
  }

  return { getStage, setStage, moveStage, getAllStages, clearAll, FUNNEL_STAGES }
}
