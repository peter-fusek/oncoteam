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


# ── Task 4: stale-while-revalidate labs/briefings/timeline ────────────


def test_swr_cache_helpers_exist():
    src = _read("composables/useSwrCache.ts")
    assert "export function swrGet" in src
    assert "export function swrSet" in src
    assert "export function swrClearAll" in src
    assert "export function swrClearPatient" in src
    assert "SWR_PREFIX" in src


def test_swr_cache_has_10min_max_age():
    """Entries older than 10 min are evicted, not deceptively served."""
    src = _read("composables/useSwrCache.ts")
    assert "10 * 60 * 1000" in src
    assert "SWR_MAX_AGE_MS" in src


def test_swr_cache_is_per_patient():
    """The cache key includes the patient id so cross-patient leak is impossible."""
    src = _read("composables/useSwrCache.ts")
    assert "patientId" in src
    assert "default" in src  # fallback for missing patient id


def test_swr_cache_opt_in_paths_include_target_three():
    """Labs / briefings / timeline — the three cards called out in #424."""
    src = _read("composables/useSwrCache.ts")
    assert "'/labs'" in src
    assert "'/briefings'" in src
    assert "'/timeline'" in src


def test_use_oncoteam_api_writes_cache_on_success():
    src = _read("composables/useOncoteamApi.ts")
    assert "swrSet" in src
    assert "isSwrPath" in src


def test_use_oncoteam_api_falls_back_to_cache_on_failure():
    """On fetch failure, fetchApi returns cached data with stale=true."""
    src = _read("composables/useOncoteamApi.ts")
    assert "swrGet" in src
    # stale / cacheAgeMs must be surfaced so the UI can render the notice
    assert "stale.value = true" in src
    assert "cacheAgeMs.value" in src


def test_layout_invalidates_swr_on_logout():
    """Logout MUST clear all SWR cache so a new user can't see prior data."""
    src = _read("layouts/default.vue")
    assert "swrClearAll" in src


def test_layout_invalidates_swr_on_patient_switch():
    """Switching patients clears the previous patient's cache."""
    src = _read("layouts/default.vue")
    assert "swrClearPatient" in src


def test_home_page_renders_stale_notice_for_three_cards():
    """Home renders the stale notice for labs, briefings, and timeline."""
    src = _read("pages/index.vue")
    assert "labsStale" in src
    assert "briefingsStale" in src
    assert "timelineStale" in src
    assert "showingCached" in src


def test_showing_cached_locale_keys_match_oncofiles_phrasing():
    """Copy mirrors oncofiles#469 phrasing for consistency across surfaces."""
    en = _read("locales/en.json")
    sk = _read("locales/sk.json")
    assert "Showing cached data" in en
    assert "reconnecting" in en
    assert "Zobrazujem uložené údaje" in sk
    assert "obnovujem spojenie" in sk


# ── Task 5: banner copy consistency ───────────────────────────────────


def test_banner_copy_matches_oncofiles_phrasing():
    """The degraded-mode banner matches oncofiles#469's cross-surface wording."""
    en = _read("locales/en.json")
    sk = _read("locales/sk.json")
    # EN short-form + countdown
    assert "Database briefly unavailable." in en
    assert "Refreshing in {seconds}s" in en
    # SK
    assert "Databáza je krátko nedostupná." in sk
    assert "Obnovujem za {seconds} s" in sk


def test_banner_covers_half_open_state():
    """Half-open has its own user-facing copy ("Reconnecting…")."""
    en = _read("locales/en.json")
    sk = _read("locales/sk.json")
    assert "apiDegradedHalfOpen" in en
    assert "Reconnecting" in en
    assert "apiDegradedHalfOpen" in sk
    assert "Obnovujem spojenie" in sk


def test_banner_component_reads_breaker_state_for_copy():
    """ApiErrorBanner picks copy based on state, not just on cooldownSeconds."""
    src = _read("components/ApiErrorBanner.vue")
    assert "breakerState" in src
    assert "half_open" in src
    assert "apiDegradedHalfOpen" in src


# ── Task 6: throttle polling during breaker open ──────────────────────


def test_fetch_api_short_circuits_when_breaker_open():
    """fetchApi skips the upstream call when cooldown_remaining_s > 2."""
    src = _read("composables/useOncoteamApi.ts")
    assert "useCircuitBreakerStatus" in src
    assert "BREAKER_POLL_SKIP_THRESHOLD_S" in src
    assert "cooldown_remaining_s" in src
    # Must check state === 'open' (not just degraded), because half_open means
    # oncofiles is already probing — let that call through.
    assert "'open'" in src


def test_fetch_api_returns_cached_during_skip():
    """During the skip window, SWR paths return cached data — not empty state."""
    src = _read("composables/useOncoteamApi.ts")
    # Anchor on the usage site inside doFetch (the `> BREAKER...` comparison),
    # not the top-level constant declaration.
    skip_block_start = src.index("> BREAKER_POLL_SKIP_THRESHOLD_S")
    skip_slice = src[skip_block_start : skip_block_start + 800]
    assert "swrGet" in skip_slice
    assert "stale.value = true" in skip_slice


def test_fetch_api_auto_refreshes_when_breaker_closes():
    """Transition open → closed triggers an automatic refresh of mounted fetches."""
    src = _read("composables/useOncoteamApi.ts")
    # Watch on breaker state is the mechanism
    assert "watch(" in src
    assert "'closed'" in src
    assert "fetched.refresh()" in src
