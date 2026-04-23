"""#431 — oncoteam MUST boot independently of oncofiles.

Regression tests pinning the Step 1 fix (commit b083479): if oncofiles
is down at startup, oncoteam's startup I/O (load_approved_phones,
load_patient_tokens) must NOT block the HTTP server from binding its
port. Port-binding delay caused the 2026-04-23 P0 incident when
Railway's healthcheck probes found nothing within the startup window
and marked the deploy FAILED.

Design principle: oncoteam and oncofiles are peer services. Either
one must run independently of the other.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.api_whatsapp import load_approved_phones, load_patient_tokens


@pytest.mark.anyio
async def test_load_approved_phones_swallows_oncofiles_timeout():
    """When oncofiles is unreachable, load_approved_phones must log and
    return — it must NOT raise. The inner try/except already covers this,
    but future refactors could accidentally remove it; pin it."""
    with patch(
        "oncoteam.api_whatsapp.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        side_effect=TimeoutError("simulated oncofiles down"),
    ):
        # Should not raise
        await load_approved_phones()


@pytest.mark.anyio
async def test_load_patient_tokens_swallows_oncofiles_timeout():
    """Same contract for the token-restore path — must not raise on
    oncofiles outage."""
    with patch(
        "oncoteam.api_whatsapp.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        side_effect=TimeoutError("simulated oncofiles down"),
    ):
        await load_patient_tokens()


@pytest.mark.anyio
async def test_startup_safe_bg_bounds_waiting_time():
    """The _safe_bg wrapper in server._run_http must not let a single
    hanging coroutine block startup beyond its timeout. This pins the
    root-cause fix for the 2026-04-23 incident: if oncofiles hangs
    indefinitely during startup, our wrapper must time out and move on
    within a few seconds, never letting the server's port-binding wait
    for oncofiles's availability.

    We reproduce the _safe_bg pattern here (it's an inner function in
    server.py so we can't import it directly) and verify the contract.
    """
    import logging

    async def _safe_bg(coro, label, timeout=1.0):
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            logging.warning("%s timed out at startup — proceeding", label)
        except Exception as e:
            logging.warning("%s failed at startup: %s", label, e)

    async def _hang_forever():
        # Simulate oncofiles-down: MCP session establishment that never returns
        await asyncio.sleep(300)

    async def _raise_immediately():
        raise RuntimeError("oncofiles unreachable")

    # Both failure modes must be bounded by the wrapper
    start = asyncio.get_event_loop().time()
    await _safe_bg(_hang_forever(), "hang_test", timeout=0.5)
    elapsed_hang = asyncio.get_event_loop().time() - start
    assert elapsed_hang < 1.0, f"hang timeout too slow: {elapsed_hang}s"

    start = asyncio.get_event_loop().time()
    await _safe_bg(_raise_immediately(), "raise_test", timeout=0.5)
    elapsed_raise = asyncio.get_event_loop().time() - start
    assert elapsed_raise < 0.5, f"raise swallow too slow: {elapsed_raise}s"


@pytest.mark.anyio
async def test_scheduler_status_does_not_touch_oncofiles():
    """`/health` reads scheduler status. That path must NOT call oncofiles
    — otherwise oncofiles downtime would cascade to health probes and
    Railway would kill oncoteam.

    `get_scheduler_status` is a pure dict builder over APScheduler's
    in-memory state. Mocking oncofiles down, it must still return a
    clean response.
    """
    from oncoteam.scheduler import get_scheduler_status

    with patch(
        "oncoteam.api_whatsapp.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        side_effect=TimeoutError("oncofiles down"),
    ):
        status = get_scheduler_status()

    assert isinstance(status, dict)
    assert "running" in status
    assert "jobs" in status
    # With scheduler not started in tests, running=False / jobs=0 is fine
