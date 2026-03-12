"""Tests for /api/autonomous/cost dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_autonomous_cost


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://oncoteam-dashboard.onrender.com"})

    return FakeRequest(query_string)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_returns_all_fields(mock_state):
    mock_state.return_value = {"month": "2026-03", "cost_usd": 12.50}
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "today_spend" in data
    assert "daily_cap" in data
    assert "mtd_spend" in data
    assert "expected_eom" in data
    assert "remaining_credit" in data
    assert "total_credit" in data
    assert "days_remaining" in data
    assert "budget_alert" in data
    assert "month" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_has_cors(mock_state):
    mock_state.return_value = {}
    request = _make_request()
    response = await api_autonomous_cost(request)
    assert (
        response.headers["access-control-allow-origin"] == "https://oncoteam-dashboard.onrender.com"
    )


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_handles_no_mtd_state(mock_state):
    mock_state.return_value = {}
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    # MTD spend should be just today's spend when no prior state
    assert data["mtd_spend"] >= 0


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_handles_error(mock_state):
    mock_state.side_effect = Exception("connection refused")
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    # Should still return 200 with defaults
    assert response.status_code == 200
    assert data["mtd_spend"] >= 0


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_budget_alert_when_low(mock_state):
    # Set MTD spend to be close to credit balance
    mock_state.return_value = {"month": "2026-03", "cost_usd": 25.0}
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    # With $33.58 credit and $25 MTD + today spend, remaining < $15 threshold
    assert data["budget_alert"] is True


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_nested_value_format(mock_state):
    """Regression: oncofiles returns {"value": {...}} wrapper around actual data."""
    mock_state.return_value = {"value": {"month": "2026-03", "cost_usd": 5.0}}
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["mtd_spend"] >= 5.0


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_agent_state", new_callable=AsyncMock)
async def test_cost_endpoint_nested_json_string_format(mock_state):
    """Regression: oncofiles may return value as JSON string."""
    mock_state.return_value = {"value": '{"month": "2026-03", "cost_usd": 3.0}'}
    request = _make_request()
    response = await api_autonomous_cost(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["mtd_spend"] >= 3.0
