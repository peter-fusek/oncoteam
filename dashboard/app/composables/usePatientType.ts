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
type CancerType = 'colorectal' | 'breast' | 'other' | 'none'

function classifyPatientType(diagnosisCode: string): PatientType {
  if (!diagnosisCode) return 'oncology' // safe fallback
  const prefix = diagnosisCode.charAt(0).toUpperCase()
  if (prefix === 'Z') return 'general'
  return 'oncology'
}

function classifyCancerType(diagnosisCode: string): CancerType {
  if (!diagnosisCode) return 'none'
  const upper = diagnosisCode.toUpperCase()
  if (upper.startsWith('C18') || upper.startsWith('C19') || upper.startsWith('C20')) return 'colorectal'
  if (upper.startsWith('C50')) return 'breast'
  if (upper.charAt(0) === 'Z') return 'none'
  return 'other'
}

export function usePatientType() {
  const { activePatientId } = useActivePatient()

  // Seeded with known patients — updated from /api/patient response
  const diagnosisCodes = useState<Record<string, string>>('patientDiagnosisCodes', () => ({
    q1b: 'C18.7',
    e5g: 'Z00.0',
    sgu: 'C50.9',
  }))

  const patientType = computed<PatientType>(() =>
    classifyPatientType(diagnosisCodes.value[activePatientId.value] || ''),
  )

  const cancerType = computed<CancerType>(() =>
    classifyCancerType(diagnosisCodes.value[activePatientId.value] || ''),
  )

  const isOncology = computed(() => patientType.value === 'oncology')
  const isGeneralHealth = computed(() => patientType.value === 'general')
  const isColorectal = computed(() => cancerType.value === 'colorectal')
  const isBreast = computed(() => cancerType.value === 'breast')

  /** Update diagnosis code cache when /api/patient response arrives. */
  function setDiagnosisCode(patientId: string, code: string) {
    diagnosisCodes.value = { ...diagnosisCodes.value, [patientId]: code }
  }

  return {
    patientType: readonly(patientType),
    cancerType: readonly(cancerType),
    isOncology: readonly(isOncology),
    isGeneralHealth: readonly(isGeneralHealth),
    isColorectal: readonly(isColorectal),
    isBreast: readonly(isBreast),
    setDiagnosisCode,
  }
}
