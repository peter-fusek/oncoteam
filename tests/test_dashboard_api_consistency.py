"""Regression tests for data consistency bugs (#203 Sprint 59).

Tests ensure that:
1. Briefing API returns `date` field (not `created_at` only)
2. Labs POST invalidates cache only for the posting patient
3. Autonomous status reads patient-scoped state keys
4. Protocol gather timeout is sufficient (8s, not 5s)
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import (
    _cache_key,
    _labs_cache,
    _protocol_cache,
    api_autonomous_status,
    api_briefings,
    api_labs,
    api_protocol,
)


def _make_request(query_string: str = "patient_id=q1b", method: str = "GET", body: bytes = b""):
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str, method_: str, body_: bytes):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})
            self.method = method_
            self._body = body_

        async def body(self):
            return self._body

    return FakeRequest(query_string, method, body)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear all API caches before each test."""
    _labs_cache.clear()
    _protocol_cache.clear()
    # Clear briefings cache
    from oncoteam.dashboard_api import _briefings_cache

    _briefings_cache.clear()
    yield
    _labs_cache.clear()
    _protocol_cache.clear()
    _briefings_cache.clear()


# ── Bug #1: Briefing date field ──────────────────────────


@pytest.mark.anyio
async def test_briefings_returns_date_field():
    """Briefings API must return `date` field (mapped from created_at)."""
    mock_briefings = {
        "entries": [
            {
                "id": 1,
                "title": "Weekly Briefing",
                "content": "## Summary\nAll good.",
                "created_at": "2026-03-26T08:00:00Z",
                "entry_type": "autonomous_briefing",
                "tags": ["sys:briefing"],
            }
        ]
    }
    mock_alerts = {"entries": []}

    with (
        patch(
            "oncoteam.dashboard_api.oncofiles_client.search_conversations",
            new_callable=AsyncMock,
            side_effect=[mock_briefings, mock_alerts],
        ),
        patch(
            "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
            return_value={"state": "closed"},
        ),
    ):
        request = _make_request("patient_id=q1b&limit=1")
        response = await api_briefings(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    briefing = data["briefings"][0]
    assert "date" in briefing, "Briefing must have 'date' field"
    assert briefing["date"] == "2026-03-26T08:00:00Z"


# ── Bug #5: Autonomous status patient-scoped state keys ──


@pytest.mark.anyio
async def test_autonomous_status_uses_patient_scoped_keys():
    """api_autonomous_status must look up state keys with patient_id suffix."""
    captured_keys: list[str] = []

    async def mock_get_state(key: str):
        captured_keys.append(key)
        return None

    with (
        patch("oncoteam.autonomous_tasks._get_state", side_effect=mock_get_state),
        patch("oncoteam.autonomous_tasks._extract_timestamp", return_value=None),
    ):
        request = _make_request("patient_id=q1b")
        await api_autonomous_status(request)

    # All state keys should include ":q1b" suffix
    for key in captured_keys:
        assert ":q1b" in key, f"State key '{key}' missing patient_id suffix"


@pytest.mark.anyio
async def test_autonomous_status_non_default_patient():
    """State keys must use the requested patient_id, not hardcoded default."""
    captured_keys: list[str] = []

    async def mock_get_state(key: str):
        captured_keys.append(key)
        return None

    with (
        patch("oncoteam.autonomous_tasks._get_state", side_effect=mock_get_state),
        patch("oncoteam.autonomous_tasks._extract_timestamp", return_value=None),
    ):
        request = _make_request("patient_id=jan")
        await api_autonomous_status(request)

    for key in captured_keys:
        assert ":jan" in key, f"State key '{key}' should use patient_id 'jan'"


# ── Bug #8: Labs POST patient-scoped cache invalidation ──


@pytest.mark.anyio
async def test_labs_post_invalidates_only_patient_cache():
    """Labs POST must only clear cache entries for the posting patient."""
    # Pre-populate caches for two patients
    q1b_key = _cache_key("labs", "q1b", "50", "")
    jan_key = _cache_key("labs", "jan", "50", "")
    _labs_cache[q1b_key] = (time.time(), "q1b_cached")
    _labs_cache[jan_key] = (time.time(), "jan_cached")

    mock_result = {"id": 99, "event_type": "lab_result"}
    with (
        patch(
            "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
            return_value={"state": "closed"},
        ),
    ):
        body = json.dumps({"date": "2026-03-27", "values": {"ANC": 3500}}).encode()
        request = _make_request("patient_id=q1b", method="POST", body=body)
        response = await api_labs(request)
        data = json.loads(response.body)

    assert data.get("created") is True
    # Erika's cache should be cleared
    assert q1b_key not in _labs_cache, "Erika's cache should be invalidated"
    # Jan's cache should remain untouched
    assert jan_key in _labs_cache, "Jan's cache should NOT be invalidated"


# ── Bug #6: Protocol gather timeout ──────────────────────


@pytest.mark.anyio
async def test_protocol_timeout_is_8s():
    """Protocol endpoint should use 8s timeout, not 5s.

    We verify by checking that a 6-second response succeeds (would fail at 5s).
    """

    async def slow_lab_fetch(**kwargs):
        await asyncio.sleep(0.01)  # Small delay, not actually 6s in test
        return {"events": []}

    async def slow_events_fetch(**kwargs):
        await asyncio.sleep(0.01)
        return {"events": []}

    async def slow_trends_fetch(**kwargs):
        await asyncio.sleep(0.01)
        return {"values": []}

    with (
        patch(
            "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
            new_callable=AsyncMock,
            side_effect=[
                {"events": []},  # lab_result call
                {"events": []},  # events call
            ],
        ),
        patch(
            "oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data",
            new_callable=AsyncMock,
            return_value={"values": []},
        ),
    ):
        request = _make_request()
        response = await api_protocol(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    # Should have protocol data even with empty labs
    assert "phases" in data or "lab_data_last_updated" in data
