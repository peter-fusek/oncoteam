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


# ── Task 3: /readiness.circuit_breaker as source of truth ─────────────


def test_readiness_proxy_endpoint_exists():
    """A dedicated server route proxies oncofiles /readiness to the browser."""
    src = _read("api/oncofiles-readiness.get.ts", base=SERVER_ROOT)
    assert "oncofilesReadinessUrl" in src
    assert "getUserSession" in src
    # Must be served as JSON passthrough — we rely on the upstream shape
    assert "circuit_breaker" in src


def test_nuxt_runtime_config_has_readiness_url():
    """Readiness URL is configurable via runtimeConfig with a sane default."""
    src = (DASHBOARD_ROOT.parent / "nuxt.config.ts").read_text()
    assert "oncofilesReadinessUrl" in src
    assert "oncofiles.com/readiness" in src


def test_breaker_composable_reads_readiness_directly():
    """useCircuitBreakerStatus no longer infers state from /api/diagnostics."""
    src = _read("composables/useCircuitBreakerStatus.ts")
    # New source of truth
    assert "/api/oncofiles-readiness" in src
    # Old inference path must be gone
    assert "/api/oncoteam/diagnostics" not in src
    # The full oncofiles breaker shape is modeled, including the new fields
    assert "cooldown_remaining_s" in src
    assert "trip_count_total" in src


def test_breaker_composable_supports_half_open_state():
    """Half-open is a real state in the oncofiles contract — don't collapse it."""
    src = _read("composables/useCircuitBreakerStatus.ts")
    assert "half_open" in src
    # degraded is true whenever state !== 'closed' (covers open + half_open)
    assert "'closed'" in src


def test_breaker_composable_animates_countdown_locally():
    """Local 1s decrement between polls keeps the countdown banner smooth."""
    src = _read("composables/useCircuitBreakerStatus.ts")
    assert "localRemaining" in src
    assert "setInterval" in src
