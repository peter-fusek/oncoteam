# Cross-tenant isolation audit — 2026-04-24

**Status**: Mitigated (Sprint 98, v0.89.0)
**Severity**: P1 (defense-in-depth; no confirmed leak in oncoteam prod, but
the anti-pattern that caused the peer incident was present latently in
oncoteam too)
**Related issues**: oncoteam#435, oncoteam#433, oncofiles#476, oncofiles#478

## Incident

On 2026-04-24 Michal Gašparík filed **oncofiles#476** reporting a
cross-patient data leak via claude.ai OAuth custom connector. An MCP
bearer that lacked an explicit patient binding was auto-resolved by
oncofiles to the "first active patient" — benign with 1 patient, a leak
with 2+.

Oncofiles shipped a hot-fix (**oncofiles#478**) the same day: any MCP
token without explicit patient binding now returns a
`__no_patient_access__` sentinel in multi-patient mode instead of
auto-resolving.

Oncoteam was affected only indirectly — the `patient_registry_sync`
agent was the single caller that relied on the default-patient
resolution, and it began receiving zero rows after the fix. Defensive
shrink-guard landed in **oncoteam#433** (commit `2655378`) turning that
silent auth regression into a loud WhatsApp alert.

## The deeper problem

The oncofiles root cause — "silently fall back to a default when
explicit scope is missing" — was present in **multiple places in
oncoteam**, not just in the peer. The oncofiles hot-fix accidentally
defended oncoteam (turning silent wrong-answer into zero rows), but
defense-in-depth requires each layer to fail closed on its own.

An audit identified 8 concrete anti-pattern sites in oncoteam:

1. `dashboard_api._get_patient_id` defaulted to `DEFAULT_PATIENT_ID`
   ("q1b") when the query parameter was absent. Any admin-key-bearing
   caller that omitted `?patient_id=` silently read q1b's data.
2. `request_context.get_token_for_patient` silently falls back to the
   admin bearer when a per-patient token isn't registered. Before
   #433/#478 the admin bearer auto-resolved to q1b; after #478 the
   bearer now returns a no-access sentinel, but the silent regression
   has no visible signal from oncoteam's side.
3. The Nuxt proxy validated *forged* `patient_id` against the session's
   allowed list but accepted *missing* `patient_id` unchallenged.
4. Five TTL caches in `dashboard_api.py` are keyed by `patient_id` but
   lacked a regression test.
5. `agent_state` keys were built ad-hoc with f-strings. New code could
   silently omit the `patient_id` prefix and land a cross-tenant key.
6. Three non-test call sites passed `token=None` to oncofiles wrapper
   functions without declaring why (all in `patient_registry_sync`,
   which is legitimately system-scoped).
7. `_get_current_patient_id()` silently defaulted to q1b when an MCP
   bearer lacked a `client_id` claim — exactly the shape of oncofiles's
   original bug.
8. No dedicated regression test suite locked the cross-tenant-isolation
   contract for future changes.

## The rule

> Any code path that needs a `patient_id` and finds none MUST refuse the
> operation (log + 4xx / raise / sentinel). Convenience defaults are
> cross-tenant leak generators the instant a second tenant exists.

Durable in `memory/feedback_fail-closed-on-missing-tenant.md`.

## Fix (Sprint 98, v0.88.0 → v0.89.0)

Eight audit items landed across two sessions (one commit per session):

| # | Surface | Change |
|---|---|---|
| 1 | `dashboard_api._get_patient_id` | Raises `_MissingPatientIdError`; `server._auth_wrap` converts to CORS-aware 400 with `code: "patient_scope_missing"` |
| 2 | `request_context.get_token_for_patient` | Logs structured `tenant_isolation.admin_bearer_fallback` warning + bumps `_ADMIN_FALLBACK_COUNTS`; surfaced in `/api/diagnostics.tenant_isolation` |
| 3 | Nuxt proxy | 400s when `patient_id` missing on patient-scoped paths; system-scoped paths allowlisted via `SYSTEM_SCOPED_PATHS` |
| 4 | Cache isolation | Parameterized test over 6 TTL caches + extras ordering |
| 5 | `agent_state` keys | `request_context.build_agent_state_key` enforces patient-OR-system scope (raises on ambiguity); migrated `funnel_audit.py` + `patient_registry_sync` hotspots |
| 6 | CI grep-gate | `scripts/check_tenant_exempt.py` + new `tenant-isolation-grep` CI job fails on any unannotated `token=None` call site |
| 7 | MCP bearer | `_get_current_patient_id` fails closed on bearer without `client_id` OR pointing at an unregistered patient; `_enforce_bearer_patient_match` is the contract for any future tool that accepts an explicit `patient_id` arg |
| 8 | Regression test | `tests/test_tenant_isolation.py` — 20 scenarios locking the contract |

## Residual risk

- **Webhook body defaults** (`api_webhooks.py:143, 318`) still fall back
  to `DEFAULT_PATIENT_ID` when the body omits `patient_id`. Webhooks are
  authenticated via admin secret + internal-only, so the blast radius is
  narrower than the dashboard/MCP surface. Tracked for Sprint 99 as a
  cleanup under the same fail-closed rule.
- **`api_whatsapp.py:382, 601`** per-message patient resolution likewise
  still falls back to q1b. Same reasoning — this lives behind Twilio
  signature validation + WhatsApp phone-number approval. Cleanup tracked
  together with the webhook path.
- **Per-patient token registry** is still env-var-driven
  (`ONCOFILES_MCP_TOKEN_<ID>`). Tracked in **oncoteam#434**
  (DB-primary read path with env-var override) — retires the ops
  friction but does NOT change the fail-closed semantics from this
  sprint.
- **OAuth client_id → patient_id mapping** is still implicit via the
  static-bearer registry. A claude.ai OAuth connector minting a bearer
  whose `client_id` is not a registered patient now fails fast (Item 7),
  but the provisioning UX (how does an OAuth client *become* a
  registered patient bearer?) remains manual.

## What we locked in

- Every patient-scoped HTTP endpoint 400s when scope is missing — the
  oncofiles#478 anti-pattern cannot form silently at the oncoteam
  layer anymore.
- `/api/diagnostics.tenant_isolation.admin_bearer_fallbacks_total` is a
  monitoring hook that makes the anti-pattern class visible before any
  leak can form.
- CI grep-gate blocks any new `token=None` caller that isn't declared
  system-scoped via `# tenant-exempt: <reason>` — the regression
  surface is fenced at PR time.
- `tests/test_tenant_isolation.py` is the permanent regression gate.
  Every scenario in it represents one of the eight audit items; if any
  one fails in future, the whole class of cross-tenant bugs regresses.

## Postmortem notes for the physician-onboarding wave

MUDr. Mináriková joins q1b as physician user (#396/#400/#402). Per
audit items 2 + 7, her onboarding path must:

- Set `ONCOFILES_MCP_TOKEN_MINARIKOVA` Railway env var **before** any
  Gate-2 operation, OR provision via DB-primary path once #434 lands.
  If missing, `get_token_for_patient("minarikova")` logs a warning and
  bumps the counter but calls still succeed (using admin bearer which
  oncofiles now rejects with no-access sentinel — so Mináriková would
  see zero data rather than q1b's data).
- Register the `PatientProfile` before any MCP session is opened for
  her bearer, otherwise `_get_current_patient_id()` now raises
  `_UnregisteredBearerPatientError` instead of silently serving q1b's
  data.

Both fail-closed paths are louder than the old silent-wrong-answer
behavior. That's the point.
