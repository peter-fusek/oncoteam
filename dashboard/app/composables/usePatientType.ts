/**
 * Patient type derivation — determines if the active patient is oncology or general health.
 *
 * Derives patient type from ICD-10 diagnosis code:
 * - Z-codes (Z00-Z99) = general health / preventive care
 * - Everything else (C, D, etc.) = oncology (default)
 *
 * Uses useState() for SSR safety. Seeded with known patients,
 * updated from /api/patient response.
 */

type PatientType = 'oncology' | 'general'

function classifyPatientType(diagnosisCode: string): PatientType {
  if (!diagnosisCode) return 'oncology' // safe fallback
  const prefix = diagnosisCode.charAt(0).toUpperCase()
  if (prefix === 'Z') return 'general'
  return 'oncology'
}

export function usePatientType() {
  const { activePatientId } = useActivePatient()

  // Seeded with known patients — updated from /api/patient response
  const diagnosisCodes = useState<Record<string, string>>('patientDiagnosisCodes', () => ({
    q1b: 'C18.7',
    e5g: 'Z00.0',
  }))

  const patientType = computed<PatientType>(() =>
    classifyPatientType(diagnosisCodes.value[activePatientId.value] || ''),
  )

  const isOncology = computed(() => patientType.value === 'oncology')
  const isGeneralHealth = computed(() => patientType.value === 'general')

  /** Update diagnosis code cache when /api/patient response arrives. */
  function setDiagnosisCode(patientId: string, code: string) {
    diagnosisCodes.value = { ...diagnosisCodes.value, [patientId]: code }
  }

  return {
    patientType: readonly(patientType),
    isOncology: readonly(isOncology),
    isGeneralHealth: readonly(isGeneralHealth),
    setDiagnosisCode,
  }
}
