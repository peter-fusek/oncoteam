/**
 * Active patient state — tracks which patient the dashboard is viewing.
 *
 * Admin (advocate) can switch between patients listed in their session.
 * Patient/doctor roles see only their own patient.
 * Patient ID is included in all API queries for multi-patient scoping.
 */

export function useActivePatient() {
  const { user } = useUserSession()

  // Initialize from session patientId, fall back to 'erika'
  const activePatientId = useState('activePatientId', () => {
    const sessionPid = user.value?.patientId as string | undefined
    return sessionPid || 'erika'
  })

  // Known patients with display info. Seeded with Erika.
  // When new patients onboard, they're added to the user's session patientIds
  // and their display info is fetched from the backend.
  const patientDisplayInfo = useState<Record<string, { name: string; diagnosis: string }>>('patientDisplayInfo', () => ({
    erika: { name: 'Erika F.', diagnosis: 'mCRC (C18.7)' },
    e5g: { name: 'Peter F.', diagnosis: 'Preventive care' },
  }))
  const { activeRole } = useUserRole()

  const canSwitchPatient = computed(() => activeRole.value === 'advocate')

  // Patient IDs this user can access (from session, set during OAuth login)
  const allowedPatientIds = computed(() => {
    const ids = user.value?.patientIds as string[] | undefined
    return ids?.length ? [...new Set(ids)] : ['erika']
  })

  const patients = computed(() =>
    allowedPatientIds.value.map(id => ({
      id,
      name: patientDisplayInfo.value[id]?.name || id,
      diagnosis: patientDisplayInfo.value[id]?.diagnosis || '',
    })),
  )

  const hasMultiplePatients = computed(() => patients.value.length > 1)

  const activePatient = computed(() =>
    patients.value.find(p => p.id === activePatientId.value) || patients.value[0],
  )

  function switchPatient(patientId: string) {
    if (!canSwitchPatient.value) return
    if (allowedPatientIds.value.includes(patientId)) {
      activePatientId.value = patientId
      // Full app reload to ensure all API data uses the new patient_id.
      // reloadNuxtApp preserves the current route while clearing all caches.
      if (import.meta.client) {
        reloadNuxtApp({ ttl: 1000 })
      }
    }
  }

  return {
    activePatientId: readonly(activePatientId),
    activePatient,
    patients,
    hasMultiplePatients,
    canSwitchPatient,
    switchPatient,
  }
}
