/**
 * Active patient state — tracks which patient the dashboard is viewing.
 *
 * Admin (advocate) can switch between patients listed in their session.
 * Patient/doctor roles see only their own patient.
 * Patient ID is included in all API queries for multi-patient scoping.
 *
 * Per-patient role (#422 Part B / Part C): session.user.patientRoles is
 * a dict mapping patient_id → role. The dropdown groups patients by
 * writable vs read-only role; mutation UIs check isReadOnlyActivePatient
 * before firing postApi.
 */

const READONLY_ROLES = new Set(['admin-readonly', 'family-readonly'])

export interface PatientListEntry {
  id: string
  name: string
  diagnosis: string
  role: string
  readOnly: boolean
}

export function useActivePatient() {
  const { user } = useUserSession()

  // Patient selection persisted via cookie (available during SSR + client)
  const patientCookie = useCookie('oncoteam_patient', { default: () => '' })

  // Initialize: cookie > session > default
  const activePatientId = useState('activePatientId', () => {
    if (patientCookie.value) return patientCookie.value
    const sessionPid = user.value?.patientId as string | undefined
    return sessionPid || 'q1b'
  })

  // Known patients with display info. Seeded with Erika.
  // When new patients onboard, they're added to the user's session patientIds
  // and their display info is fetched from the backend.
  const patientDisplayInfo = useState<Record<string, { name: string; diagnosis: string }>>('patientDisplayInfo', () => ({
    q1b: { name: 'Erika F.', diagnosis: 'mCRC (C18.7)' },
    e5g: { name: 'Peter F.', diagnosis: 'Preventive care' },
  }))
  const { activeRole } = useUserRole()

  // Patient IDs this user can access (from session, set during OAuth login)
  const allowedPatientIds = computed(() => {
    const ids = user.value?.patientIds as string[] | undefined
    return ids?.length ? [...new Set(ids)] : ['q1b']
  })

  // Per-patient role dict from session (populated by session-patch).
  // Fallback: legacy single role applied to every listed patient.
  const patientRoles = computed<Record<string, string>>(() => {
    const fromSession = user.value?.patientRoles as Record<string, string> | undefined
    if (fromSession && Object.keys(fromSession).length) return fromSession
    const legacy = (user.value?.roles as string[] | undefined)?.[0] || 'advocate'
    return Object.fromEntries(allowedPatientIds.value.map(id => [id, legacy]))
  })

  const patients = computed<PatientListEntry[]>(() =>
    allowedPatientIds.value.map((id) => {
      const role = patientRoles.value[id] || 'advocate'
      return {
        id,
        name: patientDisplayInfo.value[id]?.name || id,
        diagnosis: patientDisplayInfo.value[id]?.diagnosis || '',
        role,
        readOnly: READONLY_ROLES.has(role),
      }
    }),
  )

  // Grouped views for the dropdown: writable first, then read-only under
  // a 🔒 separator. Order within each group matches patientIds order.
  const writablePatients = computed(() => patients.value.filter(p => !p.readOnly))
  const readOnlyPatients = computed(() => patients.value.filter(p => p.readOnly))

  const hasMultiplePatients = computed(() => patients.value.length > 1)

  // Can switch patient when the user has more than one entry in the
  // dropdown, regardless of their default `activeRole`. Advocate used to
  // be the only multi-patient role; per-patient roles broaden this to
  // any user who can see multiple patients (e.g. doctor with q1b +
  // admin-readonly of nora-antalova).
  const canSwitchPatient = computed(() =>
    hasMultiplePatients.value || activeRole.value === 'advocate',
  )

  const activePatient = computed(() =>
    patients.value.find(p => p.id === activePatientId.value) || patients.value[0],
  )

  const activePatientRole = computed(() => activePatient.value?.role || 'advocate')
  const isReadOnlyActivePatient = computed(() => activePatient.value?.readOnly ?? false)

  function switchPatient(patientId: string) {
    if (!canSwitchPatient.value) return
    if (allowedPatientIds.value.includes(patientId)) {
      activePatientId.value = patientId
      patientCookie.value = patientId
      // Reload to re-create useFetch keys with new patient_id
      if (import.meta.client) reloadNuxtApp({ ttl: 1000 })
    }
  }

  return {
    activePatientId: readonly(activePatientId),
    activePatient,
    activePatientRole,
    isReadOnlyActivePatient,
    patients,
    writablePatients,
    readOnlyPatients,
    hasMultiplePatients,
    canSwitchPatient,
    switchPatient,
  }
}
