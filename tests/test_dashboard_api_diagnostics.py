"""Tests for /api/diagnostics endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_diagnostics

_CB_CLOSED = {
    "state": "closed",
    "consecutive_failures": 0,
    "threshold": 5,
    "cooldown_remaining_s": 0,
    "total_calls": 0,
    "total_errors": 0,
    "total_circuit_trips": 0,
    "call_timeout_s": 20.0,
}


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


@pytest.mark.anyio
@patch(
    "oncoteam.api_agents.oncofiles_client.get_circuit_breaker_status",
    return_value=_CB_CLOSED,
)
@patch("oncoteam.api_agents.oncofiles_client.search_activity_log", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_conversations", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_research_entries", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_diagnostics_all_healthy(
    mock_events, mock_research, mock_convos, mock_activity, _mock_cb
):
    mock_events.return_value = {"events": [{"id": 1}]}
    mock_research.return_value = {"entries": [{"id": 1}]}
    mock_convos.return_value = {"entries": []}
    mock_activity.return_value = {"entries": [{"id": 1}]}

    request = _make_request()
    response = await api_diagnostics(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["healthy"] is True
    assert len(data["checks"]) == 4
    for check in data["checks"]:
        assert check["ok"] is True
        assert "ms" in check
    assert "oncofiles_url" in data
    assert "autonomous_enabled" in data
    assert data["circuit_breaker"]["state"] == "closed"


@pytest.mark.anyio
@patch(
    "oncoteam.api_agents.oncofiles_client.get_circuit_breaker_status",
    return_value=_CB_CLOSED,
)
@patch("oncoteam.api_agents.oncofiles_client.search_activity_log", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_conversations", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_research_entries", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_diagnostics_partial_failure(
    mock_events, mock_research, mock_convos, mock_activity, _mock_cb
):
    mock_events.return_value = {"events": []}
    mock_research.side_effect = Exception("401 Unauthorized")
    mock_convos.return_value = {"entries": []}
    mock_activity.return_value = {"entries": []}

    request = _make_request()
    response = await api_diagnostics(request)
    data = json.loads(response.body)

    assert data["healthy"] is False
    failed = [c for c in data["checks"] if not c["ok"]]
    assert len(failed) == 1
    assert failed[0]["name"] == "research_entries"
    assert "401" in failed[0]["error"]


@pytest.mark.anyio
@patch(
    "oncoteam.api_agents.oncofiles_client.get_circuit_breaker_status",
    return_value=_CB_CLOSED,
)
@patch("oncoteam.api_agents.oncofiles_client.search_activity_log", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_conversations", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_research_entries", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_diagnostics_all_down(
    mock_events, mock_research, mock_convos, mock_activity, _mock_cb
):
    error = Exception("connection refused")
    mock_events.side_effect = error
    mock_research.side_effect = error
    mock_convos.side_effect = error
    mock_activity.side_effect = error

    request = _make_request()
    response = await api_diagnostics(request)
    data = json.loads(response.body)

    assert data["healthy"] is False
    assert all(not c["ok"] for c in data["checks"])


@pytest.mark.anyio
@patch(
    "oncoteam.api_agents.oncofiles_client.get_circuit_breaker_status",
    return_value=_CB_CLOSED,
)
async def test_diagnostics_has_cors(_mock_cb):
    with (
        patch(
            "oncoteam.api_agents.oncofiles_client.list_treatment_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "oncoteam.api_agents.oncofiles_client.list_research_entries",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "oncoteam.api_agents.oncofiles_client.search_conversations",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "oncoteam.api_agents.oncofiles_client.search_activity_log",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        request = _make_request()
        response = await api_diagnostics(request)
        assert response.headers["access-control-allow-origin"] == "https://dashboard.oncoteam.cloud"
