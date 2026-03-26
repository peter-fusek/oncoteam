export type FunnelStage = 'Excluded' | 'Later Line' | 'Watching' | 'Eligible Now' | 'Action Needed'

export const FUNNEL_STAGES: FunnelStage[] = ['Excluded', 'Later Line', 'Watching', 'Eligible Now', 'Action Needed']

export interface FunnelAssessment {
  stage: FunnelStage
  exclusion_reason: string | null
  next_step: string
  deadline_note: string | null
  assessed_at: string
  manually_moved?: boolean
  active?: boolean // true = actively watching, false = dimmed/passive
}

export interface FunnelLogEntry {
  datetime: string
  nct_id: string
  from: FunnelStage | 'unassessed'
  to: FunnelStage
  actor: 'auto-assess' | 'manual'
  reason: string
}

export function useFunnelStage() {
  const { activePatientId } = useActivePatient()

  function storageKey(nctId: string): string {
    return `funnel::${activePatientId.value || 'default'}::${nctId}`
  }

  function logKey(): string {
    return `funnel-log::${activePatientId.value || 'default'}`
  }

  function getStage(nctId: string): FunnelAssessment | null {
    if (!import.meta.client) return null
    try {
      const raw = localStorage.getItem(storageKey(nctId))
      return raw ? JSON.parse(raw) : null
    }
    catch { return null }
  }

  function setStage(nctId: string, assessment: FunnelAssessment, actor: 'auto-assess' | 'manual' = 'auto-assess', reason?: string): void {
    if (!import.meta.client) return
    const existing = getStage(nctId)
    const fromStage = existing?.stage ?? 'unassessed'

    // Default active to true for new assessments
    if (assessment.active === undefined) {
      assessment.active = existing?.active ?? true
    }

    localStorage.setItem(storageKey(nctId), JSON.stringify(assessment))

    // Log the movement if stage changed
    if (fromStage !== assessment.stage) {
      addLogEntry({
        datetime: new Date().toISOString(),
        nct_id: nctId,
        from: fromStage as FunnelStage | 'unassessed',
        to: assessment.stage,
        actor,
        reason: reason || assessment.next_step || 'Stage changed',
      })
    }
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
      active: existing?.active ?? true,
    }, 'manual', `Moved to ${newStage}`)
  }

  function toggleActive(nctId: string): void {
    if (!import.meta.client) return
    const existing = getStage(nctId)
    if (!existing) return
    existing.active = !(existing.active ?? true)
    localStorage.setItem(storageKey(nctId), JSON.stringify(existing))
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

  // Movement audit log
  function addLogEntry(entry: FunnelLogEntry): void {
    if (!import.meta.client) return
    try {
      const raw = localStorage.getItem(logKey())
      const log: FunnelLogEntry[] = raw ? JSON.parse(raw) : []
      log.unshift(entry) // newest first
      // Keep last 500 entries
      if (log.length > 500) log.length = 500
      localStorage.setItem(logKey(), JSON.stringify(log))
    }
    catch { /* ignore storage errors */ }
  }

  function getLog(): FunnelLogEntry[] {
    if (!import.meta.client) return []
    try {
      const raw = localStorage.getItem(logKey())
      return raw ? JSON.parse(raw) : []
    }
    catch { return [] }
  }

  return { getStage, setStage, moveStage, toggleActive, getAllStages, clearAll, getLog, FUNNEL_STAGES }
}
