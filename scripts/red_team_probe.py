#!/usr/bin/env python3
"""Red-team probe suite for the Sprints 98-100 fail-closed contracts.

Drives the backend-side portion of the red-team exercise filed as #442.
Chrome + Claude.ai MCP probes stay manual (OAuth/session-dependent); this
script automates the REST + MCP-bearer surfaces so we can re-run the same
matrix every sprint and prove no regression.

Usage:

    # Probe prod as an UNPRIVILEGED identity (no DASHBOARD_API_KEY, no bearer).
    # Proves anonymous access is blocked everywhere it should be.
    uv run python scripts/red_team_probe.py \
        --base-url https://api.oncoteam.cloud

    # Probe prod holding the shared DASHBOARD_API_KEY but NO session patient
    # scope. Proves the Nuxt-proxy ACL + body-fallback gates we shipped in
    # Sprints 99/100 fire even for a trusted key holder that has no pid.
    uv run python scripts/red_team_probe.py \
        --base-url https://api.oncoteam.cloud \
        --api-key "$DASHBOARD_API_KEY"

    # Attempt cross-tenant escalation: hold the key AND try to address q1b.
    # Each probe documents whether the defense is at the ACL layer
    # (rejected) or at the key-secrecy boundary (passes — that's #434).
    uv run python scripts/red_team_probe.py \
        --base-url https://api.oncoteam.cloud \
        --api-key "$DASHBOARD_API_KEY" \
        --attempt-cross-tenant q1b

The script exits non-zero if any PROBE marked as security-critical flips
to UNEXPECTED — that's a regression. Warnings (e.g. "E4 returns 200 with
valid key — by design until #434") print but don't fail the run.

Probe IDs match the matrix in #442 for traceability.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ProbeResult:
    probe_id: str
    description: str
    status_code: int
    passed: bool
    note: str = ""
    body_snippet: str = ""


@dataclass
class RunContext:
    base_url: str
    api_key: str | None = None
    attempt_cross_tenant: str | None = None
    results: list[ProbeResult] = field(default_factory=list)

    def headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


# ── Probe helpers ────────────────────────────────────


def _snippet(body: Any, limit: int = 160) -> str:
    try:
        s = json.dumps(body) if not isinstance(body, str) else body
    except Exception:
        s = str(body)
    return s[:limit]


def _record(
    ctx: RunContext,
    *,
    probe_id: str,
    description: str,
    resp: httpx.Response,
    expect_status: int | tuple[int, ...],
    note: str = "",
) -> ProbeResult:
    codes = (expect_status,) if isinstance(expect_status, int) else expect_status
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    passed = resp.status_code in codes
    result = ProbeResult(
        probe_id=probe_id,
        description=description,
        status_code=resp.status_code,
        passed=passed,
        note=note,
        body_snippet=_snippet(body),
    )
    ctx.results.append(result)
    return result


# ── Anonymous probes (no API key) ────────────────────


async def probe_anon_health(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Shallow /health is intentionally open for Railway liveness."""
    resp = await client.get(f"{ctx.base_url}/health")
    _record(
        ctx,
        probe_id="A-HEALTH",
        description="anonymous GET /health — should 200, no patient identifiers",
        resp=resp,
        expect_status=200,
    )


async def probe_anon_health_deep(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Sprint 99 S1 #438 bug 1 — /health/deep must 401 unauth."""
    resp = await client.get(f"{ctx.base_url}/health/deep")
    _record(
        ctx,
        probe_id="A-HEALTH-DEEP",
        description="anonymous GET /health/deep — must 401 per #438 bug 1",
        resp=resp,
        expect_status=401,
    )


async def probe_anon_api_patient(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Every /api/* route under _auth_wrap must 401 without a key."""
    resp = await client.get(f"{ctx.base_url}/api/patient?patient_id=q1b")
    _record(
        ctx,
        probe_id="A-API-PATIENT",
        description="anonymous GET /api/patient — must 401",
        resp=resp,
        expect_status=401,
    )


async def probe_anon_doc_webhook(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """POST /api/internal/document-webhook — must 401 without key."""
    resp = await client.post(
        f"{ctx.base_url}/api/internal/document-webhook",
        json={"document_id": 999_999, "patient_id": "q1b"},
    )
    _record(
        ctx,
        probe_id="A-DOC-WEBHOOK",
        description="anonymous POST /api/internal/document-webhook — must 401",
        resp=resp,
        expect_status=401,
    )


# ── Authenticated-but-no-tenant probes (API key only) ─


async def probe_auth_missing_patient_id_get(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Sprint 98 #435 — GET patient-scoped endpoints without ?patient_id= must 400."""
    if not ctx.api_key:
        return
    resp = await client.get(f"{ctx.base_url}/api/timeline", headers=ctx.headers())
    result = _record(
        ctx,
        probe_id="AUTH-GET-NO-PID",
        description=(
            "authenticated GET /api/timeline WITHOUT ?patient_id= — must 400 "
            "patient_scope_missing per #435 Item 1"
        ),
        resp=resp,
        expect_status=400,
    )
    # Extra check: code must match
    if result.passed:
        try:
            assert json.loads(resp.content).get("code") == "patient_scope_missing"
        except (AssertionError, json.JSONDecodeError):
            result.passed = False
            result.note = "body missing code: patient_scope_missing"


async def probe_auth_webhook_no_pid(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Sprint 99 #438 bug 3 — document-webhook must 400 without body.patient_id."""
    if not ctx.api_key:
        return
    resp = await client.post(
        f"{ctx.base_url}/api/internal/document-webhook",
        json={"document_id": 999_999},
        headers=ctx.headers(),
    )
    _record(
        ctx,
        probe_id="AUTH-WEBHOOK-NO-PID",
        description=(
            "authenticated POST /api/internal/document-webhook WITHOUT body.patient_id — "
            "must 400 per #438 bug 3"
        ),
        resp=resp,
        expect_status=400,
    )


async def probe_auth_trigger_agent_no_pid(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Sprint 99 — trigger-agent for patient-scoped agent must 400 without pid."""
    if not ctx.api_key:
        return
    resp = await client.post(
        f"{ctx.base_url}/api/internal/trigger-agent",
        json={"agent_id": "daily_research"},
        headers=ctx.headers(),
    )
    _record(
        ctx,
        probe_id="AUTH-TRIGGER-NO-PID",
        description=(
            "authenticated POST /api/internal/trigger-agent daily_research WITHOUT "
            "patient_id — must 400 per #438 bug 3"
        ),
        resp=resp,
        expect_status=400,
    )


async def probe_auth_whatsapp_chat_no_pid(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Sprint 100 Pattern C — whatsapp-chat must 400 without body.patient_id."""
    if not ctx.api_key:
        return
    resp = await client.post(
        f"{ctx.base_url}/api/internal/whatsapp-chat",
        json={"message": "hi", "phone": "+421xxx", "lang": "sk"},
        headers=ctx.headers(),
    )
    _record(
        ctx,
        probe_id="AUTH-WA-CHAT-NO-PID",
        description=(
            "authenticated POST /api/internal/whatsapp-chat WITHOUT patient_id — "
            "must 400 per #440 Pattern C"
        ),
        resp=resp,
        expect_status=400,
    )


# ── Cross-tenant escalation (API key + foreign patient_id) ─


async def probe_cross_tenant_get(client: httpx.AsyncClient, ctx: RunContext) -> None:
    """Hold API key + request a specific foreign patient_id.

    The API key is the admin-tier shared secret; a holder CAN legitimately
    address any patient. This probe does NOT fail if it returns 200 —
    documented as the E4 key-secrecy boundary in #442. Result is reported
    as WARNING, tracked for #434 (DB-primary signed per-patient sub-tokens).
    """
    if not ctx.api_key or not ctx.attempt_cross_tenant:
        return
    pid = ctx.attempt_cross_tenant
    resp = await client.get(f"{ctx.base_url}/api/patient?patient_id={pid}", headers=ctx.headers())
    result = _record(
        ctx,
        probe_id="CROSS-TENANT-GET",
        description=(
            f"authenticated GET /api/patient?patient_id={pid} — WARNING: "
            "admin-key holder can address any patient until #434 ships "
            "signed per-patient sub-tokens. Not a regression."
        ),
        resp=resp,
        expect_status=(200, 401, 403, 400),
        note="warning-level — key-secrecy boundary (#434)",
    )
    # Downgrade from failure to warning.
    result.passed = True  # The defense here is key secrecy, not ACL.


# ── Runner ───────────────────────────────────────────


async def run(ctx: RunContext) -> int:
    async with httpx.AsyncClient(timeout=15) as client:
        # Always-on probes
        await probe_anon_health(client, ctx)
        await probe_anon_health_deep(client, ctx)
        await probe_anon_api_patient(client, ctx)
        await probe_anon_doc_webhook(client, ctx)

        # API-key probes
        if ctx.api_key:
            await probe_auth_missing_patient_id_get(client, ctx)
            await probe_auth_webhook_no_pid(client, ctx)
            await probe_auth_trigger_agent_no_pid(client, ctx)
            await probe_auth_whatsapp_chat_no_pid(client, ctx)

        # Cross-tenant escalation
        if ctx.attempt_cross_tenant:
            await probe_cross_tenant_get(client, ctx)

    # Report
    print(f"\n{'=' * 80}")
    print(f"Red-team probe report — {ctx.base_url}")
    print(f"{'=' * 80}")
    n_pass = sum(1 for r in ctx.results if r.passed)
    n_fail = len(ctx.results) - n_pass
    for r in ctx.results:
        sym = "✓" if r.passed else "✗"
        label = "PASS" if r.passed else "FAIL"
        if "warning" in r.note.lower():
            sym, label = "⚠", "WARN"
        print(f"{sym} [{label}] {r.probe_id:22s} → {r.status_code}  {r.description[:80]}")
        if r.note:
            print(f"        note: {r.note}")
        if not r.passed or "warning" in r.note.lower():
            print(f"        body: {r.body_snippet[:120]}")
    print(f"{'=' * 80}")
    print(f"Total: {len(ctx.results)}   Pass: {n_pass}   Fail: {n_fail}")
    return 1 if n_fail else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--base-url",
        default="https://api.oncoteam.cloud",
        help="Backend base URL (default: prod)",
    )
    p.add_argument("--api-key", help="DASHBOARD_API_KEY (optional — enables AUTH-* probes)")
    p.add_argument(
        "--attempt-cross-tenant",
        metavar="PATIENT_ID",
        help="Attempt cross-tenant read for this patient_id (requires --api-key)",
    )
    args = p.parse_args()
    ctx = RunContext(
        base_url=args.base_url.rstrip("/"),
        api_key=args.api_key,
        attempt_cross_tenant=args.attempt_cross_tenant,
    )
    return asyncio.run(run(ctx))


if __name__ == "__main__":
    sys.exit(main())
