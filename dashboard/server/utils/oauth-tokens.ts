import { randomBytes } from 'node:crypto'

interface OAuthToken {
  patientId: string
  createdAt: number
}

const TOKEN_TTL_MS = 30 * 60 * 1000 // 30 minutes
const tokens = new Map<string, OAuthToken>()

function cleanupExpired(): void {
  const now = Date.now()
  for (const [token, data] of tokens) {
    if (now - data.createdAt > TOKEN_TTL_MS) {
      tokens.delete(token)
    }
  }
}

export function createOAuthToken(patientId: string): string {
  cleanupExpired()
  const token = randomBytes(32).toString('hex')
  tokens.set(token, { patientId, createdAt: Date.now() })
  return token
}

export function resolveOAuthToken(token: string): string | null {
  cleanupExpired()
  const data = tokens.get(token)
  if (!data) return null
  // Single-use: delete after resolution
  tokens.delete(token)
  return data.patientId
}
