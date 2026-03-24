/**
 * Runtime set of admin-approved WhatsApp phone numbers.
 * Phones added here bypass the allowlist after completing onboarding.
 * This is in-memory only — cleared on server restart.
 */
const approvedPhones = new Set<string>()

export function addApprovedPhone(phone: string): void {
  approvedPhones.add(phone)
}

export function isApproved(phone: string): boolean {
  return approvedPhones.has(phone)
}

export function getApprovedPhones(): string[] {
  return [...approvedPhones]
}
