/**
 * Active patient state — tracks which patient the dashboard is viewing.
 *
 * Admin (advocate) can switch between patients.
 * Patient/doctor roles see only their own patient.
 * Patient ID is included in all API queries for multi-patient scoping.
 */

const activePatientId = ref('erika')

// Known patients — seeded with Erika, expanded when new patients onboard.
// Future: fetch from backend /api/patients endpoint.
const patients = ref<Array<{ id: string; name: string; diagnosis: string }>>([
  { id: 'erika', name: 'Erika Fusekova', diagnosis: 'mCRC (C18.7)' },
])

export function useActivePatient() {
  const { activeRole } = useUserRole()

  const canSwitchPatient = computed(() => activeRole.value === 'advocate')

  const activePatient = computed(() =>
    patients.value.find(p => p.id === activePatientId.value) || patients.value[0],
  )

  const hasMultiplePatients = computed(() => patients.value.length > 1)

  function switchPatient(patientId: string) {
    if (!canSwitchPatient.value) return
    const exists = patients.value.some(p => p.id === patientId)
    if (exists) {
      activePatientId.value = patientId
    }
  }

  return {
    activePatientId: readonly(activePatientId),
    activePatient,
    patients: readonly(patients),
    hasMultiplePatients,
    canSwitchPatient,
    switchPatient,
  }
}
