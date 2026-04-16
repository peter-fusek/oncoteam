"""Load tests: simulate 10 concurrent dashboard users.

Verifies:
1. No cross-patient data leakage under concurrency
2. Request deduplication works (1 oncofiles call per cache key)
3. Per-patient rate limiting is independent
4. All responses arrive within 5s
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from oncoteam import dashboard_api as mod
from oncoteam import oncofiles_client


def _make_request(patient_id: str = "q1b"):
    """Create a mock Starlette Request with query params."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/timeline",
        "query_string": f"patient_id={patient_id}&lang=sk".encode(),
        "headers": [(b"origin", b"https://dashboard.oncoteam.cloud")],
    }
    req = Request(scope)
    return req


@pytest.fixture(autouse=True)
def _clear_all_state():
    """Clear all caches, rate limiters, and pending requests between tests."""
    mod._protocol_cache.clear()
    mod._timeline_cache.clear()
    mod._briefings_cache.clear()
    mod._labs_cache.clear()
    mod._documents_cache.clear()
    mod._pending_requests.clear()
    mod._rate_timestamps.clear()
    mod._rate_global.clear()
    mod._expensive_timestamps.clear()
    yield
    mod._pending_requests.clear()


@pytest.mark.asyncio
async def test_10_users_same_patient_dedup():
    """10 users requesting same patient's timeline = 1 oncofiles call."""
    call_count = 0

    async def mock_list_events(**kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)  # Simulate network delay
        return {"events": [{"id": 1, "event_type": "chemo", "event_date": "2026-03-01"}]}

    with patch.object(oncofiles_client, "list_treatment_events", side_effect=mock_list_events):
        requests = [_make_request("q1b") for _ in range(10)]
        start = time.monotonic()
        results = await asyncio.gather(
            *[mod.api_timeline(req) for req in requests],
            return_exceptions=True,
        )
        elapsed = time.monotonic() - start

    # All 10 should succeed
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 10, f"Expected 10 successes, got {len(successes)}"

    # Deduplication: should be 1 call (or 2 if cache miss + 1 pending)
    assert call_count <= 2, f"Expected <=2 oncofiles calls (dedup), got {call_count}"

    # All should complete within 5s
    assert elapsed < 5.0, f"Took {elapsed:.1f}s, expected <5s"


@pytest.mark.asyncio
async def test_10_users_different_patients_no_leakage():
    """10 users with different patient_ids get independent data."""
    call_log = []

    async def mock_list_events(**kwargs):
        patient_token = kwargs.get("token")
        call_log.append(patient_token)
        await asyncio.sleep(0.05)
        return {"events": [{"id": 1, "event_type": "chemo", "event_date": "2026-03-01"}]}

    with (
        patch.object(oncofiles_client, "list_treatment_events", side_effect=mock_list_events),
        patch("oncoteam.request_context.get_patient_token", side_effect=lambda pid: f"token_{pid}"),
    ):
        patient_ids = [f"patient_{i}" for i in range(10)]
        requests = [_make_request(pid) for pid in patient_ids]
        results = await asyncio.gather(
            *[mod.api_timeline(req) for req in requests],
            return_exceptions=True,
        )

    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 10

    # Each patient should have triggered a call with their own token
    unique_tokens = set(call_log)
    assert len(unique_tokens) == 10, (
        f"Expected 10 unique tokens, got {len(unique_tokens)}: {unique_tokens}"
    )


@pytest.mark.asyncio
async def test_rate_limit_per_patient_independent():
    """Patient A hitting rate limit doesn't block Patient B."""
    # Fill Patient A's rate limit bucket
    for _ in range(120):
        mod._rate_timestamps.setdefault("patient_a", mod.collections.deque()).append(time.time())
    mod._rate_global.append(time.time())

    # Patient B should NOT be rate limited (returns True = within limit)
    result = mod._check_rate_limit("patient_b")
    assert result is True, "Patient B should not be rate limited when Patient A is"

    # Patient A SHOULD be rate limited (returns False = exceeded)
    result_a = mod._check_rate_limit("patient_a")
    assert result_a is False, "Patient A should be rate limited"


@pytest.mark.asyncio
async def test_cache_isolation_under_concurrency():
    """Concurrent requests for different patients don't share cache entries."""
    call_count = {"q1b": 0, "jan": 0}

    async def mock_list_events(**kwargs):
        token = kwargs.get("token")
        patient = "jan" if token == "token_jan" else "q1b"
        call_count[patient] += 1
        await asyncio.sleep(0.05)
        event = {"id": 1, "event_type": "chemo", "event_date": "2026-03-01", "patient": patient}
        return {"events": [event]}

    with (
        patch.object(oncofiles_client, "list_treatment_events", side_effect=mock_list_events),
        patch(
            "oncoteam.request_context.get_patient_token",
            side_effect=lambda pid: f"token_{pid}" if pid != "q1b" else None,
        ),
    ):
        # Interleave requests for two patients
        requests = []
        for _ in range(5):
            requests.append(("q1b", _make_request("q1b")))
            requests.append(("jan", _make_request("jan")))

        results = await asyncio.gather(
            *[mod.api_timeline(req) for _, req in requests],
            return_exceptions=True,
        )

    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 10

    # Both patients should have been called (independent caches)
    assert call_count["q1b"] >= 1, "Erika's data should have been fetched"
    assert call_count["jan"] >= 1, "Jan's data should have been fetched"
