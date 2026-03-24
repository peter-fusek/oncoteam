export interface OnboardingState {
  step: 'welcome' | 'collect_name' | 'collect_diagnosis' | 'collect_language' | 'provisioning' | 'oauth_sent' | 'awaiting_docs' | 'complete'
  phone: string
  lang: 'sk' | 'en'
  patientName?: string
  patientId?: string
  diagnosis?: string
  createdAt: number
  updatedAt: number
}

const TTL_MS = 60 * 60 * 1000 // 1 hour of inactivity

const onboardingStates = new Map<string, OnboardingState>()

function cleanupExpired(): void {
  const now = Date.now()
  for (const [phone, state] of onboardingStates) {
    if (now - state.updatedAt > TTL_MS) {
      onboardingStates.delete(phone)
    }
  }
}

export function getOnboardingState(phone: string): OnboardingState | undefined {
  cleanupExpired()
  return onboardingStates.get(phone)
}

export function setOnboardingState(phone: string, state: OnboardingState): void {
  cleanupExpired()
  onboardingStates.set(phone, state)
}

export function clearOnboardingState(phone: string): void {
  onboardingStates.delete(phone)
}

export function isOnboarding(phone: string): boolean {
  cleanupExpired()
  return onboardingStates.has(phone)
}

export function getActiveSessionCount(): number {
  cleanupExpired()
  return onboardingStates.size
}
