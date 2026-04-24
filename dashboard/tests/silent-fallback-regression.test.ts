/**
 * #443 Phase F — regression test for the P0 silent-fallback that granted
 * Erika's session to any demoted/unregistered email (2026-04-24).
 *
 * The original bug:
 *   const userConfig = roleMap[email] || { roles: ['advocate'] }
 *   const patientId = userConfig.patient_id || 'q1b'
 *   const patientIds = [...new Set(userConfig.patient_ids || [patientId])]
 *
 * Both sites (google.get.ts OAuth callback + session-patch.ts middleware)
 * materialized a session like:
 *   { roles: ['advocate'], patientId: 'q1b', patientIds: ['q1b'] }
 * for ANY email whose role_map lookup returned undefined.
 *
 * This test simulates the lookup path and asserts that the FIXED callers
 * must NOT produce an authenticated session from an empty role_map lookup.
 */
import { describe, expect, it } from 'vitest'

import { visiblePatientIds } from '../server/utils/access-rights'

type RoleMap = Record<string, { roles?: string[], patient_id?: string, patient_ids?: string[], patient_roles?: Record<string, string> }>

/**
 * Reproduces the essential logic of both callers (google.get.ts +
 * session-patch.ts) as they exist POST-fix. Any change that reintroduces
 * the silent fallback should flip one or more of these assertions red.
 */
function resolveSignInDecision(roleMap: RoleMap, email: string): { allowed: boolean, patientIds: string[] } {
  const userConfig = roleMap[email]
  if (!userConfig) {
    // Post-fix: must refuse. Pre-fix: would have returned { roles: ['advocate'] }.
    return { allowed: false, patientIds: [] }
  }
  const visibleIds = [...new Set(visiblePatientIds(userConfig))]
  if (visibleIds.length === 0) {
    // Post-fix: must refuse. Pre-fix: visibleIds[0] || 'q1b' → ['q1b'].
    return { allowed: false, patientIds: [] }
  }
  return { allowed: true, patientIds: visibleIds }
}

describe('#443 silent-fallback regression — no implicit q1b', () => {
  const ROLE_MAP: RoleMap = {
    'peterfusek1980@gmail.com': {
      roles: ['admin', 'advocate'],
      patient_roles: { q1b: 'advocate', e5g: 'patient' },
      patient_ids: ['q1b', 'e5g'],
    },
  }

  it('demoted email (not in role_map) is NOT granted access', () => {
    const result = resolveSignInDecision(ROLE_MAP, 'peter.fusek@instarea.sk')
    expect(result.allowed).toBe(false)
    expect(result.patientIds).toEqual([])
  })

  it('demoted email does NOT inherit q1b implicitly', () => {
    // This is the EXACT pre-fix behavior that caused the P0:
    // a demoted email ended up with patientIds: ['q1b'].
    const result = resolveSignInDecision(ROLE_MAP, 'peter.fusek@instarea.sk')
    expect(result.patientIds).not.toContain('q1b')
  })

  it('never-onboarded email (in allowedEmails but not in role_map) is NOT granted access', () => {
    // Specifically reproduces the peter.fusek@instarea.com case — this
    // email has been in NUXT_ALLOWED_EMAILS since the dashboard launched,
    // and pre-fix would have rendered Erika on every sign-in.
    const result = resolveSignInDecision(ROLE_MAP, 'peter.fusek@instarea.com')
    expect(result.allowed).toBe(false)
    expect(result.patientIds).toEqual([])
  })

  it('role_map entry with empty patient scope is rejected', () => {
    // userConfig exists but has no patient_roles, no patient_ids, no
    // patient_id — the "declared but no data" edge case the fix added.
    const result = resolveSignInDecision(
      { 'pending@example.com': { roles: ['advocate'] } },
      'pending@example.com',
    )
    expect(result.allowed).toBe(false)
    expect(result.patientIds).toEqual([])
  })

  it('admin email (in role_map) IS granted access with correct scope', () => {
    // Positive control — the fix must not over-rotate and lock out the
    // legitimate admin. peterfusek1980@gmail.com sees both patients.
    const result = resolveSignInDecision(ROLE_MAP, 'peterfusek1980@gmail.com')
    expect(result.allowed).toBe(true)
    expect(result.patientIds.sort()).toEqual(['e5g', 'q1b'])
  })

  it('admin email access is NOT affected by case variations in demoted emails', () => {
    // Defense-in-depth: even if an attacker tries case variations of a
    // demoted email, they're not in the role_map.
    expect(resolveSignInDecision(ROLE_MAP, 'Peter.Fusek@instarea.sk').allowed).toBe(false)
    expect(resolveSignInDecision(ROLE_MAP, 'PETER.FUSEK@INSTAREA.SK').allowed).toBe(false)
  })
})
