/**
 * Runtime set of admin-approved WhatsApp phone numbers.
 * Phones added here bypass the allowlist after completing onboarding.
 * In-memory cache — backend (oncofiles) is the source of truth.
 * If a phone is not in the local cache, we double-check with the backend
 * before routing to onboarding.
 */
const approvedPhones = new Set<string>()

export function addApprovedPhone(phone: string): void {
  approvedPhones.add(phone)
}

export function isApproved(phone: string): boolean {
  return approvedPhones.has(phone)
}

/**
 * Check backend for approved status when local cache misses.
 * Returns true if the backend confirms the phone is approved (persisted in oncofiles).
 * Caches the result locally on success.
 */
export async function checkApprovedWithBackend(
  phone: string,
  oncoteamApiUrl: string,
  apiKey: string,
): Promise<boolean> {
  if (approvedPhones.has(phone)) return true
  try {
    const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
    const result = await $fetch<{ phone: string; status: string; approved: boolean }>(
      `${oncoteamApiUrl}/api/internal/onboarding-status`,
      {
        method: 'POST',
        body: { phone },
        headers,
        timeout: 3000,
      },
    )
    if (result.approved) {
      approvedPhones.add(phone)
      return true
    }
  }
  catch {
    // Backend unreachable — fall through to onboarding
  }
  return false
}

export function getApprovedPhones(): string[] {
  return [...approvedPhones]
}
