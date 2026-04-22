"""Source-level assertions on the Nuxt dashboard codebase.

Mirrors the pattern oncofiles uses in `tests/test_dashboard.py` — read the
relevant files and assert that documented invariants are present. This lets
the CI suite catch regressions of client-side contracts (Retry-After
handling, SWR cache, breaker banner) without booting a browser.

See oncoteam#424 / oncofiles#469.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD_ROOT = Path(__file__).parent.parent / "dashboard" / "app"
SERVER_ROOT = Path(__file__).parent.parent / "dashboard" / "server"


def _read(rel: str, base: Path = DASHBOARD_ROOT) -> str:
    return (base / rel).read_text()


# ── Task 1: honor Retry-After on 503, jitter for 500/502/504 ─────────


def test_api_fetch_composable_exists():
    src = _read("composables/useApiFetch.ts")
    assert "export async function apiFetch" in src
    assert "export function parseRetryAfter" in src
    assert "export function jitterMs" in src


def test_api_fetch_parses_retry_after_both_forms():
    """parseRetryAfter accepts integer seconds OR HTTP-date per RFC 7231."""
    src = _read("composables/useApiFetch.ts")
    # integer seconds
    assert "parseInt(headerValue, 10)" in src
    # HTTP-date
    assert "Date.parse(headerValue)" in src


def test_api_fetch_503_throws_with_retry_after():
    """On 503 the helper throws { status: 503, retryAfterMs } and does NOT retry."""
    src = _read("composables/useApiFetch.ts")
    assert "resp.status === 503" in src
    assert "retryAfterMs" in src
    assert "'Retry-After'" in src
    # 503 block must throw — not `continue`
    block_start = src.index("resp.status === 503")
    block_slice = src[block_start : block_start + 400]
    assert "throw err" in block_slice
    assert "continue" not in block_slice


def test_api_fetch_jitter_bounds_match_oncofiles():
    """Jitter backoff: base 500ms, cap 5s, ±25% — matches oncofiles apiFetch."""
    src = _read("composables/useApiFetch.ts")
    # Defaults are named so regressions are obvious
    assert "baseMs = 500" in src
    assert "maxMs = 5000" in src
    assert "0.25" in src  # ±25% jitter


def test_api_fetch_transient_5xx_retry_budget():
    """500/502/504 + AbortError retry path uses jitterMs and respects retryBudget."""
    src = _read("composables/useApiFetch.ts")
    assert "resp.status === 500 || resp.status === 502 || resp.status === 504" in src
    assert "attempt < retryBudget" in src
    assert "jitterMs(attempt)" in src


def test_use_oncoteam_api_routes_through_api_fetch():
    """fetchApi uses the new apiFetch helper instead of Nuxt's retryStatusCodes."""
    src = _read("composables/useOncoteamApi.ts")
    assert "from './useApiFetch'" in src
    assert "apiFetch" in src
    # The old retry-on-503 path must be gone — banner handles retry now.
    assert "retryStatusCodes" not in src
    assert "retryDelay" not in src


def test_use_oncoteam_api_surfaces_retry_after_ms():
    """fetchApi exposes retryAfterMs so the banner can size its countdown."""
    src = _read("composables/useOncoteamApi.ts")
    assert "retryAfterMs" in src


def test_proxy_forwards_retry_after_header():
    """The Nuxt proxy forwards upstream Retry-After so the client banner is authoritative."""
    src = _read("api/oncoteam/[...path].ts", base=SERVER_ROOT)
    assert "'Retry-After'" in src
    # The header must actually be set on the event, not just read
    assert "setHeader(event, 'Retry-After'" in src
