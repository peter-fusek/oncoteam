/**
 * Structured audit logging for OAuth sign-in decisions.
 *
 * Filed as part of Sprint 101 S1.2 (post-#443 follow-up). The #443 P0
 * postmortem surfaced a forensic gap: once the silent-fallback bug was
 * fixed we could NOT determine whether peter.fusek@instarea.com had
 * ever actually signed in during the window it was exposed, because
 * Nuxt doesn't log OAuth callbacks by default. These structured events
 * close that gap going forward — every sign-in attempt emits one line
 * of grep-friendly JSON with email + outcome + role_map state.
 *
 * Emit shape is stable; downstream log-aggregation can key on `tag` +
 * `outcome`. Keep this file dependency-free so the Vitest suite can
 * import it without a Nuxt runtime.
 */

export type AuthAuditOutcome =
  | 'allowed'
  | 'rejected_no_role_map'
  | 'rejected_empty_scope'

export interface AuthAuditEvent {
  tag: 'auth.google.callback'
  email: string
  outcome: AuthAuditOutcome
  role_map_hit: boolean
  patient_count: number
  roles: string[] | null
  // `null` = env var NUXT_ALLOWED_EMAILS is unset (Peter's post-Phase-D
  // cleanup target). `true`/`false` = env var still present and the email
  // was / wasn't in it. A `true` here + `rejected_no_role_map` is the
  // exact "dual-list drift that caused #443" signal we want to catch.
  in_allowed_emails_deprecated: boolean | null
  ts: string
}

export interface BuildAuthAuditEventOpts {
  email: string
  outcome: AuthAuditOutcome
  roleMapHit: boolean
  patientCount: number
  roles?: string[] | null
  /** Override for tests; defaults to process.env.NUXT_ALLOWED_EMAILS. */
  allowedEmailsEnv?: string | undefined
  /** Override for tests; defaults to new Date().toISOString(). */
  now?: () => string
}

function parseAllowedEmails(raw: string | undefined): string[] | null {
  if (raw === undefined || raw === null) return null
  const trimmed = raw.trim()
  if (trimmed === '') return null
  return trimmed
    .split(/[,\s]+/)
    .map(s => s.trim().toLowerCase())
    .filter(Boolean)
}

export function buildAuthAuditEvent(opts: BuildAuthAuditEventOpts): AuthAuditEvent {
  const allowedEmailsRaw = opts.allowedEmailsEnv !== undefined
    ? opts.allowedEmailsEnv
    : process.env.NUXT_ALLOWED_EMAILS
  const allowedList = parseAllowedEmails(allowedEmailsRaw)
  const inAllowedEmails = allowedList === null
    ? null
    : allowedList.includes(opts.email.trim().toLowerCase())
  const ts = (opts.now || (() => new Date().toISOString()))()
  return {
    tag: 'auth.google.callback',
    email: opts.email,
    outcome: opts.outcome,
    role_map_hit: opts.roleMapHit,
    patient_count: opts.patientCount,
    roles: opts.roles ?? null,
    in_allowed_emails_deprecated: inAllowedEmails,
    ts,
  }
}

/**
 * Emit the event to stdout as a single JSON line. Separate from
 * `buildAuthAuditEvent` so the handler does one call and tests of the
 * event shape don't need to stub console.
 */
export function logAuthAuditEvent(event: AuthAuditEvent): void {
  // Single-line JSON keeps Railway log search + later log-sink ingestion
  // trivial. `console.info` (not `warn`) so it doesn't clutter error
  // dashboards — forensic signal, not an alert.
  console.info(JSON.stringify(event))
}
