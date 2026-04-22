"""Narrowed circuit-breaker trigger for oncoteam's oncofiles client.

Per oncoteam#424 Task 2 and oncofiles#469, the local breaker must trip
ONLY when oncofiles itself signals that its internal breaker is open —
generic timeouts or transient errors must not count toward the local
breaker, because that's the double-breaker amplification that produced
the false "Database under load" banner reported in #424.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam import oncofiles_client


@pytest.fixture(autouse=True)
def _reset_breaker_state():
    """Fresh breaker state per test — these globals are module-level."""
    oncofiles_client._circuit_failures = 0
    oncofiles_client._circuit_open_until = 0.0
    oncofiles_client._total_circuit_trips = 0
    oncofiles_client._total_errors = 0
    oncofiles_client._circuit_state.clear()
    yield
    oncofiles_client._circuit_state.clear()


# ── _parse_upstream_breaker_signal ──────────────────────────────────


def test_parse_upstream_breaker_recognises_canonical_phrase():
    exc = RuntimeError("Circuit breaker open — DB unavailable, retry in 30s")
    is_open, cooldown = oncofiles_client._parse_upstream_breaker_signal(exc)
    assert is_open is True
    assert cooldown == 30.0


def test_parse_upstream_breaker_parses_variable_cooldown():
    """The cooldown in the upstream message is honored verbatim."""
    exc = RuntimeError("Circuit breaker open — DB unavailable, retry in 7s")
    _, cooldown = oncofiles_client._parse_upstream_breaker_signal(exc)
    assert cooldown == 7.0


def test_parse_upstream_breaker_recognises_rest_error_body():
    """Matches the 503 body string oncofiles emits from _circuit_breaker_503."""
    exc = RuntimeError("Database briefly unavailable, please retry in ~30s")
    is_open, cooldown = oncofiles_client._parse_upstream_breaker_signal(exc)
    assert is_open is True
    # The tilde form should still parse the number
    assert cooldown == 30.0


def test_parse_upstream_breaker_ignores_generic_timeout():
    exc = TimeoutError()
    is_open, cooldown = oncofiles_client._parse_upstream_breaker_signal(exc)
    assert is_open is False
    assert cooldown is None


def test_parse_upstream_breaker_ignores_connection_reset():
    exc = ConnectionError("server reset the connection")
    assert oncofiles_client._parse_upstream_breaker_signal(exc) == (False, None)


def test_parse_upstream_breaker_ignores_generic_runtime_error():
    exc = RuntimeError("something else broke")
    assert oncofiles_client._parse_upstream_breaker_signal(exc) == (False, None)


# ── _call_with_retry breaker accounting ─────────────────────────────


async def test_transient_timeout_does_not_trip_breaker():
    """A plain timeout after all retries must NOT flip the local breaker.

    Before #424 this would increment _circuit_failures and, after 5 calls,
    open the local breaker — showing "Database under load" to the user
    while oncofiles itself was perfectly healthy.
    """
    mock_client = AsyncMock()
    mock_client.call_tool.side_effect = TimeoutError()

    with (
        patch("oncoteam.oncofiles_client._get_client", AsyncMock(return_value=mock_client)),
        patch("oncoteam.oncofiles_client._invalidate_client", AsyncMock()),
    ):
        for _ in range(10):  # well past CIRCUIT_BREAKER_THRESHOLD
            with pytest.raises(asyncio.TimeoutError):
                await oncofiles_client._call_with_retry("get_patient_context", {}, None)

    circuit = oncofiles_client._get_circuit(None)
    assert circuit["failures"] == 0
    assert circuit["open_until"] == 0.0
    assert oncofiles_client._circuit_failures == 0
    assert oncofiles_client._total_circuit_trips == 0


async def test_upstream_breaker_signal_trips_local_breaker():
    """Explicit upstream breaker error MUST trip the local breaker + set cooldown."""
    mock_client = AsyncMock()
    mock_client.call_tool.side_effect = RuntimeError(
        "Circuit breaker open — DB unavailable, retry in 30s"
    )

    with (
        patch("oncoteam.oncofiles_client._get_client", AsyncMock(return_value=mock_client)),
        patch("oncoteam.oncofiles_client._invalidate_client", AsyncMock()),
        pytest.raises(RuntimeError),
    ):
        await oncofiles_client._call_with_retry("get_patient_context", {}, None)

    circuit = oncofiles_client._get_circuit(None)
    assert circuit["failures"] == 1
    assert circuit["open_until"] > 0
    assert oncofiles_client._total_circuit_trips == 1


async def test_upstream_breaker_cooldown_matches_retry_after():
    """Local cooldown mirrors the upstream-declared Retry-After, not a fixed 30s."""
    import time

    mock_client = AsyncMock()
    mock_client.call_tool.side_effect = RuntimeError(
        "Circuit breaker open — DB unavailable, retry in 7s"
    )

    now = time.monotonic()
    with (
        patch("oncoteam.oncofiles_client._get_client", AsyncMock(return_value=mock_client)),
        patch("oncoteam.oncofiles_client._invalidate_client", AsyncMock()),
        pytest.raises(RuntimeError),
    ):
        await oncofiles_client._call_with_retry("get_patient_context", {}, None)

    circuit = oncofiles_client._get_circuit(None)
    remaining = circuit["open_until"] - now
    # Should be close to 7 (not 30, which is the default fallback)
    assert 5.0 < remaining < 9.0


async def test_mixed_transient_and_success_keeps_breaker_closed():
    """If a call eventually succeeds (or fails transiently) the local breaker
    stays closed, even after thousands of transient blips."""
    mock_client = AsyncMock()
    # alternate timeouts and successes
    call_count = {"n": 0}

    async def flaky(name, args, **kw):
        call_count["n"] += 1
        if call_count["n"] % 2 == 0:
            raise TimeoutError()
        return AsyncMock(data={"ok": True})

    mock_client.call_tool.side_effect = flaky

    with (
        patch("oncoteam.oncofiles_client._get_client", AsyncMock(return_value=mock_client)),
        patch("oncoteam.oncofiles_client._invalidate_client", AsyncMock()),
        patch("oncoteam.oncofiles_client._parse_result", lambda r: {"ok": True}),
    ):
        for _ in range(20):
            with contextlib.suppress(TimeoutError):
                await oncofiles_client._call_with_retry("get_patient_context", {}, None)

    circuit = oncofiles_client._get_circuit(None)
    assert circuit["open_until"] == 0.0
    assert oncofiles_client._total_circuit_trips == 0
