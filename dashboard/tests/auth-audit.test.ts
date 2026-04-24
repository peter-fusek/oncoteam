/**
 * Sprint 101 S1.2 — tests for the OAuth audit-log event shape.
 *
 * The handler in server/routes/auth/google.get.ts emits one structured
 * event per sign-in attempt. These tests lock in the shape so a future
 * refactor can't silently drop a field or change an outcome string that
 * downstream log aggregation depends on.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { buildAuthAuditEvent, logAuthAuditEvent } from '../server/utils/auth-audit'

const FIXED_TS = '2026-04-25T00:00:00.000Z'
const fixedNow = () => FIXED_TS

describe('buildAuthAuditEvent — shape + outcome handling', () => {
  it('allowed outcome — captures roles + patient_count', () => {
    const event = buildAuthAuditEvent({
      email: 'peterfusek1980@gmail.com',
      outcome: 'allowed',
      roleMapHit: true,
      patientCount: 2,
      roles: ['admin', 'advocate'],
      allowedEmailsEnv: undefined,
      now: fixedNow,
    })
    expect(event).toEqual({
      tag: 'auth.google.callback',
      email: 'peterfusek1980@gmail.com',
      outcome: 'allowed',
      role_map_hit: true,
      patient_count: 2,
      roles: ['admin', 'advocate'],
      in_allowed_emails_deprecated: null,
      ts: FIXED_TS,
    })
  })

  it('rejected_no_role_map — roles field is null, patient_count 0', () => {
    const event = buildAuthAuditEvent({
      email: 'peter.fusek@instarea.sk',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: undefined,
      now: fixedNow,
    })
    expect(event.outcome).toBe('rejected_no_role_map')
    expect(event.role_map_hit).toBe(false)
    expect(event.patient_count).toBe(0)
    expect(event.roles).toBeNull()
  })

  it('rejected_empty_scope — role_map hit but no patient_ids', () => {
    const event = buildAuthAuditEvent({
      email: 'pending@example.com',
      outcome: 'rejected_empty_scope',
      roleMapHit: true,
      patientCount: 0,
      roles: ['advocate'],
      allowedEmailsEnv: undefined,
      now: fixedNow,
    })
    expect(event.outcome).toBe('rejected_empty_scope')
    expect(event.role_map_hit).toBe(true)
    expect(event.roles).toEqual(['advocate'])
    expect(event.patient_count).toBe(0)
  })

  it('tag is pinned to auth.google.callback across outcomes', () => {
    // Downstream log aggregators key on this string; changing it is a
    // breaking change.
    for (const outcome of ['allowed', 'rejected_no_role_map', 'rejected_empty_scope'] as const) {
      const event = buildAuthAuditEvent({
        email: 'x@test',
        outcome,
        roleMapHit: outcome !== 'rejected_no_role_map',
        patientCount: outcome === 'allowed' ? 1 : 0,
        now: fixedNow,
      })
      expect(event.tag).toBe('auth.google.callback')
    }
  })
})

describe('buildAuthAuditEvent — NUXT_ALLOWED_EMAILS deprecation signal', () => {
  it('null when env var is unset (post-Phase-D cleanup target)', () => {
    const event = buildAuthAuditEvent({
      email: 'anyone@example.com',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: undefined,
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBeNull()
  })

  it('null when env var is set but empty string', () => {
    const event = buildAuthAuditEvent({
      email: 'anyone@example.com',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: '',
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBeNull()
  })

  it('true when email IS in the deprecated list — the dual-list drift signal', () => {
    // This is the exact forensic signal the #443 postmortem wanted: an
    // email rejected at role_map but still present in the legacy list
    // means a historical exposure window was possible.
    const event = buildAuthAuditEvent({
      email: 'peter.fusek@instarea.com',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: 'peterfusek1980@gmail.com,peter.fusek@instarea.com',
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBe(true)
  })

  it('false when email is NOT in the deprecated list', () => {
    const event = buildAuthAuditEvent({
      email: 'random@attacker.com',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: 'peterfusek1980@gmail.com',
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBe(false)
  })

  it('case-insensitive match (user email might be any case)', () => {
    const event = buildAuthAuditEvent({
      email: 'Peter.Fusek@Instarea.COM',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: 'peter.fusek@instarea.com',
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBe(true)
  })

  it('handles whitespace-separated list (Railway sometimes renders that way)', () => {
    const event = buildAuthAuditEvent({
      email: 'peter.fusek@instarea.com',
      outcome: 'rejected_no_role_map',
      roleMapHit: false,
      patientCount: 0,
      allowedEmailsEnv: 'peterfusek1980@gmail.com\npeter.fusek@instarea.com',
      now: fixedNow,
    })
    expect(event.in_allowed_emails_deprecated).toBe(true)
  })

  it('reads process.env.NUXT_ALLOWED_EMAILS when override not provided', () => {
    const original = process.env.NUXT_ALLOWED_EMAILS
    process.env.NUXT_ALLOWED_EMAILS = 'from-env@example.com'
    try {
      const event = buildAuthAuditEvent({
        email: 'from-env@example.com',
        outcome: 'rejected_no_role_map',
        roleMapHit: false,
        patientCount: 0,
        now: fixedNow,
      })
      expect(event.in_allowed_emails_deprecated).toBe(true)
    }
    finally {
      if (original === undefined) delete process.env.NUXT_ALLOWED_EMAILS
      else process.env.NUXT_ALLOWED_EMAILS = original
    }
  })
})

describe('logAuthAuditEvent — single-line JSON output', () => {
  let infoSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
  })
  afterEach(() => {
    infoSpy.mockRestore()
  })

  it('emits one JSON.stringify line to console.info', () => {
    const event = buildAuthAuditEvent({
      email: 'peterfusek1980@gmail.com',
      outcome: 'allowed',
      roleMapHit: true,
      patientCount: 2,
      roles: ['admin', 'advocate'],
      allowedEmailsEnv: undefined,
      now: fixedNow,
    })
    logAuthAuditEvent(event)
    expect(infoSpy).toHaveBeenCalledTimes(1)
    const [line] = infoSpy.mock.calls[0]
    // Must be valid JSON and a single line (no literal newlines) so it
    // stays grep-friendly in Railway logs.
    expect(typeof line).toBe('string')
    expect((line as string).includes('\n')).toBe(false)
    const parsed = JSON.parse(line as string)
    expect(parsed.tag).toBe('auth.google.callback')
    expect(parsed.outcome).toBe('allowed')
  })

  it('emits to info, not warn or error (forensic signal, not alert)', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      logAuthAuditEvent(
        buildAuthAuditEvent({
          email: 'x@test',
          outcome: 'allowed',
          roleMapHit: true,
          patientCount: 1,
          now: fixedNow,
        }),
      )
      expect(infoSpy).toHaveBeenCalledTimes(1)
      expect(warnSpy).not.toHaveBeenCalled()
      expect(errorSpy).not.toHaveBeenCalled()
    }
    finally {
      warnSpy.mockRestore()
      errorSpy.mockRestore()
    }
  })
})
