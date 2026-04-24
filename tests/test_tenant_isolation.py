"""Cross-tenant isolation regression suite (#435 Item 8).

This file is the durable gate against the class of bugs that caused
oncofiles#478 — silent fallback to a default patient when tenant scope is
missing. Each scenario asserts that a forged or mis-wired patient scope
either raises or returns empty data, never returns another patient's data.

See `memory/feedback_fail-closed-on-missing-tenant.md` for the rule and
`docs/incidents/2026-04-24-cross-tenant-isolation-audit.md` for the
postmortem that triggered the sprint.

Scenarios landed in Session 1 (skeleton — rest land in Session 2):
- missing patient_id → 400 (Item 1 backend enforcement)
- cache keys for patient A and patient B are disjoint (Item 4)
- `get_token_for_patient` admin-bearer fallback bumps the counter (Item 2)

Session 2 will add:
- session-forge: authenticated-as-q1b cannot forge patient_id=e5g on any
  patient-scoped endpoint (Item 3 + Item 8)
- MCP bearer mismatch: bearer for e5g cannot call tools with patient_id=q1b
  (Item 7)
- agent_state cross-patient invisibility (Item 5)
- rate-limiter bucket isolation
"""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers, QueryParams

from oncoteam.dashboard_api import (
    _cache_key,
    _get_patient_id,
    _MissingPatientIdError,
    api_timeline,
)
from oncoteam.request_context import (
    get_tenant_isolation_stats,
    get_token_for_patient,
    reset_tenant_isolation_stats,
)

# ── Fixtures ──────────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal Request stand-in for unit tests that only exercise query_params."""

    def __init__(self, query_string: str = ""):
        self.query_params = QueryParams(query_string)
        self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})


@pytest.fixture(autouse=True)
def _reset_tenant_stats():
    """Counter is module-global; reset between tests."""
    reset_tenant_isolation_stats()
    yield
    reset_tenant_isolation_stats()


# ── Item 1 — missing patient_id → 400 ─────────────────────────────────


def test_get_patient_id_raises_when_query_param_missing():
    """#435 Item 1 — fail closed on a patient-scoped endpoint called without ?patient_id=.

    Before this change the helper defaulted to DEFAULT_PATIENT_ID ("q1b"),
    which meant any admin-key caller that forgot the query param silently
    read q1b's data. The new contract is that the helper raises a typed
    exception so the central `_auth_wrap` can emit a CORS-aware 400.
    """
    req = _FakeRequest(query_string="")
    with pytest.raises(_MissingPatientIdError):
        _get_patient_id(req)


def test_get_patient_id_raises_on_empty_string_value():
    """?patient_id= (key present, value empty) is treated as missing."""
    req = _FakeRequest(query_string="patient_id=")
    with pytest.raises(_MissingPatientIdError):
        _get_patient_id(req)


def test_get_patient_id_returns_scoped_value_when_present():
    """Happy path — helper returns exactly what the query carries."""
    req = _FakeRequest(query_string="patient_id=e5g")
    assert _get_patient_id(req) == "e5g"


@pytest.mark.anyio
async def test_api_timeline_returns_400_when_patient_id_missing():
    """End-to-end — the central auth wrapper surfaces the 400 to the caller.

    This is the contract the Nuxt proxy relies on (#435 Item 3): the backend
    never silently serves data when scope is missing, so even a mis-wired
    dashboard composable can't leak another patient's timeline.
    """
    req = _FakeRequest(query_string="")

    # Direct handler invocation bypasses _auth_wrap, so the exception
    # flows out. We assert the raise here; the _auth_wrap→400 path is
    # covered in Session 2's proxy-level end-to-end test.
    with pytest.raises(_MissingPatientIdError):
        await api_timeline(req)


# ── Item 4 — cache cross-tenant isolation ─────────────────────────────


@pytest.mark.parametrize(
    "prefix",
    ["timeline", "labs", "briefings", "protocol", "documents", "facts"],
)
def test_cache_keys_are_disjoint_across_patients(prefix: str):
    """Per-patient cache keys must not collide.

    If this test ever fails, patient A's cached response could be served
    to patient B — the exact shape of the cross-tenant leak oncofiles#478
    fixed at the peer layer. Parameterized over every TTL cache in
    dashboard_api.py that is keyed per-patient.
    """
    key_a = _cache_key(prefix, "q1b", "limit=10")
    key_b = _cache_key(prefix, "e5g", "limit=10")
    assert key_a != key_b, f"{prefix} cache keys must differ per patient"
    assert "q1b" in key_a
    assert "e5g" in key_b


def test_cache_key_does_not_mix_extras_across_patients():
    """Cache-key extras are positional; verify order + scope preserved."""
    # Same extras, different patient: keys must be distinct.
    a = _cache_key("labs", "q1b", "a", "b")
    b = _cache_key("labs", "e5g", "a", "b")
    assert a != b
    # Same patient, different extras: keys must be distinct.
    assert _cache_key("labs", "q1b", "a") != _cache_key("labs", "q1b", "b")


# ── Item 2 — admin-bearer fallback counter ────────────────────────────


def test_admin_bearer_fallback_increments_counter_for_unregistered_patient(
    monkeypatch: pytest.MonkeyPatch,
):
    """#435 Item 2 — every admin-bearer fallback must be visible in diagnostics.

    When a non-q1b patient_id has no registered per-patient token,
    `get_token_for_patient` returns None and the caller uses the admin
    bearer. Oncofiles#478 now rejects that with a no-access sentinel,
    but oncoteam must still surface the regression via a counter before
    the peer-layer defense hides it.
    """
    # Simulate a patient whose per-patient token isn't registered.
    monkeypatch.setattr("oncoteam.patient_context.get_patient_token", lambda _pid: None)

    assert get_tenant_isolation_stats()["admin_bearer_fallbacks_total"] == 0

    # Three fallback observations for patient "unregistered" + one for "other".
    for _ in range(3):
        assert get_token_for_patient("unregistered") is None
    assert get_token_for_patient("other") is None

    stats = get_tenant_isolation_stats()
    assert stats["admin_bearer_fallbacks_total"] == 4
    assert stats["admin_bearer_fallbacks_by_patient"]["unregistered"] == 3
    assert stats["admin_bearer_fallbacks_by_patient"]["other"] == 1


def test_q1b_does_not_trigger_fallback_counter():
    """q1b → admin bearer is the intentional design, not a fallback."""
    assert get_token_for_patient("q1b") is None
    assert get_tenant_isolation_stats()["admin_bearer_fallbacks_total"] == 0


def test_empty_patient_id_does_not_trigger_fallback_counter():
    """Empty patient_id is handled upstream by _get_patient_id (400).

    The fallback counter is specifically for the "non-q1b with missing
    per-patient token" case; the empty-string path is separately guarded.
    """
    assert get_token_for_patient("") is None
    assert get_tenant_isolation_stats()["admin_bearer_fallbacks_total"] == 0
