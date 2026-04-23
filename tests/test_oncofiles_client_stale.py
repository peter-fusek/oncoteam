"""#432 — oncoteam must auto-recover when oncofiles restarts and leaves
the persistent MCP client with a dead session.

Before the fix (commit pending), `fastmcp.Client.__aenter__` would hang
indefinitely on `ready_event.wait()` when the peer had died. Every
request then piled on the module-level lock, saturated the oncofiles
semaphores, and every downstream dashboard call returned 502 until
oncoteam itself was rebooted. /imaging was the canonical symptom since
it calls `search_documents` (heavy tool, single slot, no cache).

The fix: bound `__aenter__` with `CONNECT_TIMEOUT=5s` in `_get_client`,
raise a clearly-marked `TimeoutError`, and have `_call_with_retry`
grant one extra attempt when it sees that specific error — even for
heavy tools that normally don't retry.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam import oncofiles_client


@pytest.fixture(autouse=True)
def _clear_client_state():
    """Reset module-level client singleton + lock between tests so each
    test gets a clean slate. The persistent-clients dict is the main
    thing we're testing, so leakage would confuse results."""
    oncofiles_client._persistent_clients.clear()
    oncofiles_client._client_lock = None
    yield
    oncofiles_client._persistent_clients.clear()
    oncofiles_client._client_lock = None


@pytest.mark.anyio
async def test_get_client_times_out_on_dead_peer():
    """When __aenter__ hangs forever (oncofiles just restarted and the
    SSE session never becomes ready), _get_client must raise within
    CONNECT_TIMEOUT seconds rather than blocking indefinitely."""

    class HangingClient:
        async def __aenter__(self):
            # Mimic fastmcp.Client when peer is dead: wait forever.
            await asyncio.sleep(300)
            return self

        async def __aexit__(self, *a):
            return None

    with (
        patch("oncoteam.oncofiles_client.Client", return_value=HangingClient()),
        patch("oncoteam.oncofiles_client.CONNECT_TIMEOUT", 0.2),
        patch("oncoteam.oncofiles_client.ONCOFILES_MCP_URL", "https://fake.example/mcp"),
    ):
        start = asyncio.get_event_loop().time()
        with pytest.raises(TimeoutError) as ei:
            await oncofiles_client._get_client(token="test-token")
        elapsed = asyncio.get_event_loop().time() - start

    # Must fail fast — not queue indefinitely
    assert elapsed < 1.0, f"_get_client blocked too long: {elapsed}s"
    # And carry the specific signal string that _call_with_retry looks for
    assert "handshake timed out" in str(ei.value)


@pytest.mark.anyio
async def test_get_client_creates_fresh_after_invalidate():
    """After a handshake-timeout failure invalidates the singleton, the
    next _get_client call must create a fresh Client — not reuse the
    dead one."""

    call_count = 0

    class OkClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    def client_factory(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return OkClient()

    with (
        patch("oncoteam.oncofiles_client.Client", side_effect=client_factory),
        patch("oncoteam.oncofiles_client.ONCOFILES_MCP_URL", "https://fake.example/mcp"),
    ):
        c1 = await oncofiles_client._get_client(token="t")
        assert call_count == 1
        # Second call within same token reuses the singleton
        c2 = await oncofiles_client._get_client(token="t")
        assert call_count == 1
        assert c1 is c2
        # After invalidate, a new factory call happens
        await oncofiles_client._invalidate_client(token="t")
        c3 = await oncofiles_client._get_client(token="t")
        assert call_count == 2
        assert c3 is not c1


@pytest.mark.anyio
async def test_call_with_retry_recovers_from_handshake_timeout():
    """End-to-end: a handshake-timeout on the first attempt must
    trigger _invalidate_client + retry, succeeding on the second
    attempt once the peer is back. Applies to heavy tools too
    (max_attempts=1 normally) per #432."""

    attempt_count = 0

    class FlakyClient:
        """First instance hangs on __aenter__ (peer dead), second
        works and returns a parsed tool result."""

        def __init__(self, instance_id: int):
            self.instance_id = instance_id

        async def __aenter__(self):
            if self.instance_id == 1:
                # Dead peer — hang past CONNECT_TIMEOUT
                await asyncio.sleep(300)
            return self

        async def __aexit__(self, *a):
            return None

        async def call_tool(self, name, args):
            mock_result = MagicMock()
            mock_result.content = [MagicMock(text='{"entries": ["ok"]}')]
            return mock_result

    factory_calls = 0

    def factory(*_a, **_kw):
        nonlocal factory_calls
        factory_calls += 1
        return FlakyClient(factory_calls)

    async def inc_attempts(name, args, token):
        nonlocal attempt_count
        attempt_count += 1
        # Delegate to the real _call_with_retry path
        raise NotImplementedError

    # Use a heavy tool name to prove the handshake-extra-attempt rule
    # kicks in even when max_attempts=1.
    with (
        patch("oncoteam.oncofiles_client.Client", side_effect=factory),
        patch("oncoteam.oncofiles_client.CONNECT_TIMEOUT", 0.2),
        patch("oncoteam.oncofiles_client.ONCOFILES_MCP_URL", "https://fake.example/mcp"),
        patch("oncoteam.oncofiles_client._check_rss_backoff", new_callable=AsyncMock),
    ):
        result = await oncofiles_client._call_with_retry(
            "search_documents",  # heavy tool
            {"text": "q"},
            token="t",
        )

    assert factory_calls == 2, f"expected fresh client on retry, got {factory_calls} factory calls"
    assert isinstance(result, dict) and result.get("entries") == ["ok"]
