/**
 * #443 Phase F — unit tests for the access-control helpers.
 *
 * The helpers in server/utils/access-rights.ts are pure functions over
 * a RoleMap object; the P0 bug was in CALLERS (google.get.ts, session-
 * patch.ts) that bypassed these helpers with `||` fallbacks. These
 * tests lock in the helpers' expected shape so future refactors can't
 * silently regress the invariants the callers now depend on.
 */
import { describe, expect, it } from 'vitest'

import {
  buildPatientRoles,
  getRoleForPatient,
  isReadOnlyRole,
  visiblePatientIds,
} from '../server/utils/access-rights'

describe('access-rights helpers', () => {
  describe('visiblePatientIds', () => {
    it('returns empty array for undefined userConfig', () => {
      expect(visiblePatientIds(undefined)).toEqual([])
    })

    it('returns empty array for userConfig with no patient_id / patient_ids / patient_roles', () => {
      // Exactly the shape the pre-fix silent fallback created:
      // `{ roles: ['advocate'] }`. Pre-fix, the caller then did
      // `visibleIds[0] || 'q1b'` — which became 'q1b'. Post-fix, the
      // caller sees [] and throws 403. This test enforces the helper
      // doesn't start inventing patient IDs.
      expect(visiblePatientIds({ roles: ['advocate'] })).toEqual([])
    })

    it('returns patient_ids from legacy flat shape', () => {
      expect(
        visiblePatientIds({
          roles: ['advocate'],
          patient_ids: ['q1b', 'e5g'],
        }),
      ).toEqual(['q1b', 'e5g'])
    })

    it('returns keys of patient_roles (new #422 shape)', () => {
      expect(
        visiblePatientIds({
          patient_roles: { q1b: 'advocate', e5g: 'patient' },
        }),
      ).toEqual(['q1b', 'e5g'])
    })

    it('unions patient_roles + patient_ids without duplicates', () => {
      expect(
        visiblePatientIds({
          patient_roles: { q1b: 'advocate' },
          patient_ids: ['q1b', 'e5g'],
        }).sort(),
      ).toEqual(['e5g', 'q1b'])
    })

    it('returns [patient_id] when only the legacy singular is set', () => {
      expect(visiblePatientIds({ patient_id: 'q1b' })).toEqual(['q1b'])
    })
  })

  describe('getRoleForPatient', () => {
    it('returns null for undefined userConfig', () => {
      expect(getRoleForPatient(undefined, 'q1b')).toBeNull()
    })

    it('prefers patient_roles new shape over legacy flat roles', () => {
      const uc = {
        roles: ['advocate'],
        patient_ids: ['q1b', 'e5g'],
        patient_roles: { q1b: 'doctor', e5g: 'patient' },
      }
      expect(getRoleForPatient(uc, 'q1b')).toBe('doctor')
      expect(getRoleForPatient(uc, 'e5g')).toBe('patient')
    })

    it('falls back to legacy roles[0] when patient_id is in patient_ids', () => {
      expect(
        getRoleForPatient(
          { roles: ['advocate'], patient_ids: ['q1b'] },
          'q1b',
        ),
      ).toBe('advocate')
    })

    it('returns null when patient_id is not visible to this user', () => {
      expect(
        getRoleForPatient(
          { patient_roles: { q1b: 'advocate' } },
          'e5g',
        ),
      ).toBeNull()
    })

    it('returns null when userConfig has no roles at all', () => {
      expect(getRoleForPatient({ patient_ids: ['q1b'] }, 'q1b')).toBeNull()
    })
  })

  describe('buildPatientRoles', () => {
    it('returns empty object for undefined userConfig', () => {
      expect(buildPatientRoles(undefined)).toEqual({})
    })

    it('derives per-patient roles from patient_roles', () => {
      expect(
        buildPatientRoles({
          patient_roles: { q1b: 'advocate', e5g: 'patient' },
        }),
      ).toEqual({ q1b: 'advocate', e5g: 'patient' })
    })

    it('fills legacy patient_ids with roles[0]', () => {
      expect(
        buildPatientRoles({
          roles: ['advocate'],
          patient_ids: ['q1b', 'e5g'],
        }),
      ).toEqual({ q1b: 'advocate', e5g: 'advocate' })
    })
  })

  describe('isReadOnlyRole', () => {
    it('identifies admin-readonly as read-only', () => {
      expect(isReadOnlyRole('admin-readonly')).toBe(true)
      expect(isReadOnlyRole('family-readonly')).toBe(true)
    })

    it('identifies writable roles as NOT read-only', () => {
      expect(isReadOnlyRole('advocate')).toBe(false)
      expect(isReadOnlyRole('patient')).toBe(false)
      expect(isReadOnlyRole('doctor')).toBe(false)
    })

    it('handles null/undefined/empty', () => {
      expect(isReadOnlyRole(null)).toBe(false)
      expect(isReadOnlyRole(undefined)).toBe(false)
      expect(isReadOnlyRole('')).toBe(false)
    })
  })
})
