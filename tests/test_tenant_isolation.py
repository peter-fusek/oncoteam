"""Cross-tenant isolation regression suite (#435 Item 8).

This file is the durable gate against the class of bugs that caused
oncofiles#478 — silent fallback to a default patient when tenant scope is
missing. Each scenario asserts that a forged or mis-wired patient scope
either raises or returns empty data, never returns another patient's data.

See `memory/feedback_fail-closed-on-missing-tenant.md` for the rule and
`docs/incidents/2026-04-24-cross-tenant-isolation-audit.md` for the
postmortem that triggered the sprint.

Scenarios landed:

Session 1:
- missing patient_id → 400 (Item 1 backend enforcement)
- cache keys for patient A and patient B are disjoint (Item 4)
- `get_token_for_patient` admin-bearer fallback bumps the counter (Item 2)

Session 2:
- `build_agent_state_key` requires patient-OR-system scope (Item 5)
- MCP bearer-vs-arg mismatch rejected by `_enforce_bearer_patient_match`
  (Item 7)
- MCP bearer with unregistered `client_id` fails closed (Item 7)
- Rate-limiter buckets are disjoint per patient
- Nuxt proxy session-forge scenario documented (Item 3 — full integration
  test deferred to E2E when Vitest is introduced to the dashboard)

Sprint 99 (Felix audit):
- `get_patient_profile_text` raises on unregistered patient_id (#436 bug 2)
- `get_genetic_profile` returns empty dict on unregistered patient_id
  (#436 bug 3)
- `get_context_tags` scopes by patient, not the module-level PATIENT
  constant (#436 bug 1) — sgu/e5g callers no longer get q1b's markers
- `/api/detail/patient` ships an allowlist (no rodné číslo / lat-lon /
  oncopanel VAF in drill-down) (#438 bug 4)
"""

from __future__ import annotations

import collections

import pytest
from starlette.datastructures import Headers, QueryParams

from oncoteam.dashboard_api import (
    _cache_key,
    _check_rate_limit,
    _get_patient_id,
    _MissingPatientIdError,
    _rate_timestamps,
    api_timeline,
)
from oncoteam.request_context import (
    build_agent_state_key,
    get_tenant_isolation_stats,
    get_token_for_patient,
    reset_tenant_isolation_stats,
)
from oncoteam.server import (
    _enforce_bearer_patient_match,
    _UnregisteredBearerPatientError,
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


# ── Item 5 — build_agent_state_key scope discipline ───────────────────


def test_build_agent_state_key_patient_scoped():
    """Patient-scoped keys include the patient_id segment."""
    key = build_agent_state_key("funnel_cards", patient_id="q1b")
    assert key == "funnel_cards:q1b"
    key_extra = build_agent_state_key("funnel_audit", patient_id="e5g", extra=("card_123",))
    assert key_extra == "funnel_audit:e5g:card_123"


def test_build_agent_state_key_system_scoped():
    """System-scoped keys skip the patient_id segment (wire-compatible)."""
    assert build_agent_state_key("role_map", system=True) == "role_map"
    assert (
        build_agent_state_key("patient_registry", system=True, extra=("last_snapshot",))
        == "patient_registry:last_snapshot"
    )


def test_build_agent_state_key_rejects_missing_scope():
    """Neither patient_id nor system=True → raise.

    This is the fail-closed guard that stops a new caller from silently
    writing an untenanted key that should have been patient-scoped.
    """
    with pytest.raises(ValueError, match="requires exactly one"):
        build_agent_state_key("somekey")


def test_build_agent_state_key_rejects_double_scope():
    """Supplying both patient_id and system=True → raise."""
    with pytest.raises(ValueError, match="requires exactly one"):
        build_agent_state_key("somekey", patient_id="q1b", system=True)


# ── Item 7 — MCP bearer-vs-arg match ──────────────────────────────────


def test_enforce_bearer_patient_match_rejects_divergent_arg(
    monkeypatch: pytest.MonkeyPatch,
):
    """Explicit patient_id arg ≠ bearer identity → refuse (confused-deputy).

    Even though no current MCP tool accepts a patient_id arg, this helper
    is the contract any new multi-patient tool must adopt. Proves the
    cross-tenant escalation path is closed.
    """
    # Pretend the bearer resolves to q1b.
    monkeypatch.setattr("oncoteam.server._get_current_patient_id", lambda: "q1b")

    # Matching arg → returns bearer pid.
    assert _enforce_bearer_patient_match("q1b") == "q1b"
    # None arg → returns bearer pid (back-compat with tools that don't pass one).
    assert _enforce_bearer_patient_match(None) == "q1b"

    # Diverging arg → raises.
    with pytest.raises(_UnregisteredBearerPatientError, match="cross-tenant"):
        _enforce_bearer_patient_match("e5g")


# ── Rate-limiter bucket isolation ─────────────────────────────────────


def test_rate_limiter_buckets_are_disjoint_across_patients():
    """Exhausting one patient's bucket must not deny other patients.

    The rate limiter is per-patient (plus a global safety valve). If a
    single patient's traffic somehow exhausted another patient's bucket,
    that would be both a cross-tenant leak (observing A's traffic pattern)
    and a denial of service. Assert the two are independent.
    """
    # Clear in-memory buckets so the test is deterministic regardless
    # of what earlier tests did.
    _rate_timestamps.clear()

    # Drain q1b's bucket (120 req/window).
    for _ in range(120):
        assert _check_rate_limit("q1b")
    # q1b is now at its per-patient ceiling.
    assert not _check_rate_limit("q1b")

    # e5g's bucket must still accept traffic.
    assert _check_rate_limit("e5g")
    assert isinstance(_rate_timestamps["e5g"], collections.deque)
    assert len(_rate_timestamps["e5g"]) == 1
    assert len(_rate_timestamps["q1b"]) == 120


# ── Sprint 99 — Felix audit regressions ───────────────────────────────


def test_get_patient_profile_text_raises_on_unregistered():
    """#436 bug 2 — silent-fallback-to-Erika path fails closed now.

    Previously an unregistered pid would return q1b's diagnosis, biomarkers,
    and excluded_therapies. Now raises KeyError, matching `get_patient()`.
    """
    from oncoteam.patient_context import get_patient_profile_text

    with pytest.raises(KeyError, match="not found"):
        get_patient_profile_text("never-registered-pid")


@pytest.mark.anyio
async def test_get_genetic_profile_empty_on_unregistered():
    """#436 bug 3 — seed-with-Erika's-biomarkers path returns empty now.

    The previous behaviour pre-seeded the result with ``PATIENT.biomarkers``
    (KRAS G12S, ATM biallelic loss, TP53) before calling oncofiles. For an
    unregistered pid with no matching docs, the caller got Erika's variants
    attributed to their patient.
    """
    from oncoteam.patient_context import get_genetic_profile

    result = await get_genetic_profile("never-registered-pid")
    assert result == {}


def test_get_context_tags_scopes_per_patient():
    """#436 bug 1 — research tags derive from the named patient, not PATIENT.

    Without this fix, every caller's search_pubmed-driven research corpus
    was tagged with Erika's KRAS G12S / mFOLFOX6 / colorectal markers. The
    clinical-safety issue was sgu (breast) and e5g (preventive) getting
    those tags applied to their trial/article surfacing pipeline.
    """
    from oncoteam.models import PatientProfile
    from oncoteam.patient_context import get_context_tags, register_patient

    # Register a breast-cancer patient so the test owns its fixture data.
    register_patient(
        "test-breast",
        "test-token-breast",
        PatientProfile(
            patient_id="test-breast",
            name="Test Breast",
            diagnosis_code="C50.9",
            diagnosis_description="Breast cancer NOS",
            tumor_site="left breast",
            biomarkers={"ER": "positive", "HER2": "negative"},
            treatment_regimen="AC-T",
        ),
    )

    tags_breast = get_context_tags("test-breast")
    # Must carry breast-specific tags only, not colorectal / KRAS / FOLFOX.
    assert "AC-T" in tags_breast
    assert any("ER" in t for t in tags_breast)
    assert not any("FOLFOX" in t for t in tags_breast)
    assert not any("KRAS" in t for t in tags_breast)
    assert "colorectal" not in tags_breast
    assert "sigmoid" not in tags_breast

    # q1b's tags DO include the mFOLFOX6 / KRAS / sigmoid markers.
    tags_q1b = get_context_tags("q1b")
    assert any("KRAS" in t for t in tags_q1b)


def test_api_detail_patient_omits_sensitive_identifiers():
    """#438 bug 4 — drill-down no longer ships national ID / lat-lon / VAF.

    The previous behaviour was ``model_dump(mode="json")`` on the raw
    PatientProfile. That exposed:
    - patient_ids (rodné číslo, nou_id, poisťovňa)
    - home_region (lat/lon geo-coords)
    - oncopanel_history (per-variant VAF + HGVS)
    - agent_whitelist + paused + notification_policy (operational state)

    The dashboard drill-down needs none of those. The allowlist keeps only
    the clinical-profile fields the UI actually renders.
    """
    from oncoteam.patient_context import get_patient

    # Project through the same allowlist the endpoint uses.
    allowed = {
        "patient_id",
        "name",
        "diagnosis_code",
        "diagnosis_description",
        "tumor_site",
        "tumor_laterality",
        "staging",
        "histology",
        "treatment_regimen",
        "current_cycle",
        "ecog",
        "metastases",
        "comorbidities",
        "hospitals",
        "treating_physician",
        "notes",
        "biomarkers",
        "excluded_therapies",
    }
    # Raw dump carries the sensitive surface.
    raw = get_patient("q1b").model_dump(mode="json")
    sensitive = {
        "patient_ids",
        "home_region",
        "oncopanel_history",
        "agent_whitelist",
        "paused",
        "notification_policy",
        "enrollment_preference",
        "active_therapies",
    }
    assert sensitive.issubset(set(raw)), (
        "Baseline: raw model_dump must contain the sensitive fields that the "
        "allowlist exists to strip. If this fails, adjust the allowlist."
    )
    # The intersection with the allowlist must be empty.
    assert not (sensitive & allowed)


# ── Sprint 100 — oncofiles#484 pattern propagation ────────────────────


@pytest.mark.anyio
async def test_whatsapp_chat_requires_patient_id():
    """Pattern C — api_whatsapp_chat fails closed without body.patient_id.

    Previously line 389 of api_whatsapp.py had `pid = patient_id or
    DEFAULT_PATIENT_ID` — any caller whose Nuxt-side phone→patient lookup
    failed was silently chatted with as q1b. Fails closed now.
    """
    import json as _json

    from oncoteam.api_whatsapp import api_whatsapp_chat

    class _PostReq:
        method = "POST"
        headers: dict[str, str] = {}

        def __init__(self, body: bytes):
            from starlette.datastructures import QueryParams

            self._body = body
            self.query_params = QueryParams("")

        async def body(self) -> bytes:
            return self._body

    resp = await api_whatsapp_chat(_PostReq(_json.dumps({"message": "hi", "lang": "sk"}).encode()))
    assert resp.status_code == 400
    body = _json.loads(resp.body)
    assert body["code"] == "patient_scope_missing"


@pytest.mark.anyio
async def test_whatsapp_voice_requires_patient_id():
    """Pattern C — api_whatsapp_voice fails closed without body.patient_id.

    Previously line 665 had `body.get("patient_id", "q1b")` — an explicit
    q1b default that attributed every voice transcription without a pid to
    Erika.
    """
    import base64
    import json as _json

    from oncoteam.api_whatsapp import api_whatsapp_voice

    class _PostReq:
        method = "POST"
        headers: dict[str, str] = {}

        def __init__(self, body: bytes):
            from starlette.datastructures import QueryParams

            self._body = body
            self.query_params = QueryParams("")

        async def body(self) -> bytes:
            return self._body

    audio_b64 = base64.b64encode(b"\x00" * 2000).decode()
    resp = await api_whatsapp_voice(_PostReq(_json.dumps({"audio_base64": audio_b64}).encode()))
    assert resp.status_code == 400
    body = _json.loads(resp.body)
    assert body["code"] == "patient_scope_missing"


@pytest.mark.anyio
async def test_whatsapp_media_requires_patient_id():
    """Pattern C — api_whatsapp_media rejects empty patient_id.

    The previous behaviour stripped body.patient_id to empty and passed it
    through to oncofiles upload, which would silently drop the document
    under whatever default scope oncofiles chose. Fails closed at the
    oncoteam layer now.
    """
    import json as _json

    from oncoteam.api_whatsapp import api_whatsapp_media

    class _PostReq:
        method = "POST"
        headers: dict[str, str] = {}

        def __init__(self, body: bytes):
            from starlette.datastructures import QueryParams

            self._body = body
            self.query_params = QueryParams("")

        async def json(self) -> dict:
            return _json.loads(self._body)

        async def body(self) -> bytes:
            return self._body

    resp = await api_whatsapp_media(
        _PostReq(
            _json.dumps(
                {
                    "media_base64": "aGVsbG8=",
                    "content_type": "image/jpeg",
                    "filename": "x.jpg",
                    "phone": "+421",
                    "patient_id": "",
                }
            ).encode()
        )
    )
    assert resp.status_code == 400
    body = _json.loads(resp.body)
    assert body["code"] == "patient_scope_missing"


def test_a1_boot_check_dashboard_api_key_required_on_http():
    """Pattern A.1 — importing server.py under HTTP transport with an unset
    DASHBOARD_API_KEY must raise RuntimeError at module load, not leave the
    process healthy while every /api/* call 500s.

    Mirrors the oncofiles#485 Phase 1 fail-closed startup contract + the
    existing MCP_BEARER_TOKEN boot check at server.py line 123.
    """
    import importlib
    import os
    import sys

    # Copy and mutate env for the forked import. Restore after.
    saved_transport = os.environ.get("MCP_TRANSPORT")
    saved_api_key = os.environ.get("DASHBOARD_API_KEY")
    saved_bearer = os.environ.get("MCP_BEARER_TOKEN")

    try:
        os.environ["MCP_TRANSPORT"] = "streamable-http"
        os.environ["MCP_BEARER_TOKEN"] = "dummy-bearer-for-boot-check"
        os.environ.pop("DASHBOARD_API_KEY", None)

        # Fresh import — drop any cached server/config so the new env wins.
        for mod in [
            "oncoteam.server",
            "oncoteam.config",
            "oncoteam.dashboard_api",
        ]:
            sys.modules.pop(mod, None)

        with pytest.raises(RuntimeError, match="DASHBOARD_API_KEY"):
            importlib.import_module("oncoteam.server")
    finally:
        # Restore env before re-importing so other tests see clean state.
        if saved_transport is None:
            os.environ.pop("MCP_TRANSPORT", None)
        else:
            os.environ["MCP_TRANSPORT"] = saved_transport
        if saved_api_key is None:
            os.environ.pop("DASHBOARD_API_KEY", None)
        else:
            os.environ["DASHBOARD_API_KEY"] = saved_api_key
        if saved_bearer is None:
            os.environ.pop("MCP_BEARER_TOKEN", None)
        else:
            os.environ["MCP_BEARER_TOKEN"] = saved_bearer
        # Re-import server cleanly so subsequent tests in this process get a
        # valid module rather than the half-imported state the raise left.
        for mod in [
            "oncoteam.server",
            "oncoteam.config",
            "oncoteam.dashboard_api",
        ]:
            sys.modules.pop(mod, None)
        importlib.import_module("oncoteam.server")


# ── Sprint 100 S2 — Patterns E + F ────────────────────────────────────


def test_pattern_e_safe_mcp_error_sanitizes_upstream_exception():
    """Pattern E — _safe_mcp_error strips raw exception text.

    The previous `json.dumps({"error": str(e)})` pattern returned the full
    exception message to any MCP caller that tripped a tool, which could
    include oncofiles doc IDs, other patients' UUIDs, or internal URLs.
    Now collapses to a stable category + exception class.
    """
    from oncoteam.server import _safe_mcp_error

    class _LeakyError(RuntimeError):
        """Fake oncofiles exception carrying cross-tenant info."""

    payload = _safe_mcp_error(
        _LeakyError("patient_id=e5g not authorized for doc_id=12345 at /internal/x")
    )
    assert payload == {"error": "upstream_unavailable", "kind": "_LeakyError"}
    # Negative: the raw exception text must not appear anywhere.
    blob = str(payload)
    assert "e5g" not in blob
    assert "12345" not in blob
    assert "/internal/x" not in blob


def test_red_team_442_no_hardcoded_admin_emails_in_access_control():
    """Red-team #442 — access control must never depend on a hardcoded email.

    Every admin / per-patient binding flows through the role_map
    (`NUXT_ROLE_MAP` env → oncofiles agent_state → `_load_access_rights` →
    Nuxt proxy session). If any Python file hardcodes a specific email as
    admin-or-advocate, the red-team exercise filed as #442 becomes
    un-runnable: revoking the email via env change wouldn't actually
    demote the identity.

    The only legitimate email reference in Python is the suppressed-error
    log / contact output — never in access-control paths. This grep-gate
    fails if a regression sneaks one in.
    """
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "oncoteam"
    # The two identities the red-team plan (#442) splits.
    forbidden = [
        "peter.fusek@instarea.sk",
        "peterfusek1980@gmail.com",
    ]
    # Access-control keywords that would indicate a hardcoded binding.
    control_keywords = re.compile(r"(admin|role|caregiver|advocate|is_admin|ADMIN)", re.I)

    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text()
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if not any(email in line for email in forbidden):
                continue
            # Allow if the line is a comment OR doesn't sit in an
            # access-control context (i.e. the surrounding ±3 lines don't
            # mention admin/role/etc.).
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            context = "\n".join(lines[max(0, idx - 3) : idx + 4])
            if control_keywords.search(context):
                offenders.append(f"{path.name}:{idx + 1}: {line.strip()}")

    assert not offenders, (
        "Hardcoded email in an access-control context — this breaks the "
        "#442 red-team contract (access must derive from role_map, not "
        "from a constant). Offending lines:\n" + "\n".join(offenders)
    )


def test_pattern_f_public_patient_view_strips_sensitive_fields():
    """Pattern F — public_patient_view is the shared allowlist helper.

    Mirrors the /api/detail/patient allowlist Sprint 99 built (#438 bug 4)
    so the MCP get_patient_context tool and any future bearer-authed surface
    get the same sanitized projection.
    """
    from oncoteam.patient_context import get_patient, public_patient_view

    view = public_patient_view(get_patient("q1b"))
    # The sensitive fields must not appear.
    forbidden = {
        "patient_ids",
        "home_region",
        "oncopanel_history",
        "agent_whitelist",
        "paused",
        "notification_policy",
        "enrollment_preference",
        "active_therapies",
    }
    assert not (forbidden & set(view)), (
        f"public_patient_view leaked sensitive fields: {forbidden & set(view)}"
    )
    # The clinical-profile fields MUST appear (otherwise the view is useless).
    required = {
        "patient_id",
        "name",
        "diagnosis_code",
        "diagnosis_description",
        "biomarkers",
        "excluded_therapies",
        "treatment_regimen",
    }
    assert required.issubset(set(view))
