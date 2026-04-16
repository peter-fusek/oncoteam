"""Tests for GET/POST /api/research/funnel-stages endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_funnel_stages_get, api_funnel_stages_save


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


def _make_post_request(body: dict, query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, b: dict, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers(
                {
                    "origin": "https://dashboard.oncoteam.cloud",
                    "content-type": "application/json",
                    "content-length": str(len(json.dumps(b))),
                }
            )
            self._body = json.dumps(b).encode()

        async def body(self):
            return self._body

    return FakeRequest(body, query_string)


# ── GET tests ────────────────────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_get_returns_stages(mock_get):
    """Should return stages dict from oncofiles agent state."""
    mock_get.return_value = {
        "result": {"NCT001": {"stage": "Watching"}, "NCT002": {"stage": "Excluded"}}
    }
    response = await api_funnel_stages_get(_make_request())
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "stages" in data
    assert data["stages"]["NCT001"]["stage"] == "Watching"
    mock_get.assert_called_once_with("funnel_stages:q1b", token=None)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_get_accepts_value_key(mock_get):
    """Should also accept 'value' key (not just 'result') from oncofiles."""
    mock_get.return_value = {"value": {"NCT003": {"stage": "Eligible Now"}}}
    response = await api_funnel_stages_get(_make_request())
    data = json.loads(response.body)
    assert data["stages"]["NCT003"]["stage"] == "Eligible Now"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_get_parses_json_string(mock_get):
    """Should JSON-decode the value when stored as a string."""
    mock_get.return_value = {"result": json.dumps({"NCT004": {"stage": "Excluded"}})}
    response = await api_funnel_stages_get(_make_request())
    data = json.loads(response.body)
    assert data["stages"]["NCT004"]["stage"] == "Excluded"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
    new_callable=AsyncMock,
    side_effect=Exception("oncofiles down"),
)
async def test_funnel_stages_get_returns_empty_on_error(mock_get):
    """Should return empty stages dict (not 5xx) when oncofiles fails."""
    response = await api_funnel_stages_get(_make_request())
    data = json.loads(response.body)
    assert response.status_code == 200
    assert data["stages"] == {}


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_get_respects_patient_id(mock_get):
    """Should use the patient_id from query params in the state key."""
    mock_get.return_value = {"result": {}}
    response = await api_funnel_stages_get(_make_request("patient_id=e5g"))
    assert response.status_code == 200
    mock_get.assert_called_once_with("funnel_stages:e5g", token=None)


# ── POST tests ───────────────────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.set_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_save_persists(mock_set):
    """Should call set_agent_state and return count."""
    mock_set.return_value = {}
    stages = {"NCT001": {"stage": "Watching"}, "NCT002": {"stage": "Excluded"}}
    response = await api_funnel_stages_save(_make_post_request({"stages": stages}))
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["count"] == 2
    mock_set.assert_called_once_with("funnel_stages:q1b", stages, token=None)


@pytest.mark.anyio
async def test_funnel_stages_save_rejects_non_dict():
    """Should return 400 when stages is not a dict."""
    response = await api_funnel_stages_save(
        _make_post_request({"stages": ["NCT001"]})
    )
    data = json.loads(response.body)
    assert response.status_code == 400
    assert "error" in data


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.set_agent_state",
    new_callable=AsyncMock,
    side_effect=Exception("write failed"),
)
async def test_funnel_stages_save_returns_500_on_error(mock_set):
    """Should return 500 when oncofiles fails."""
    response = await api_funnel_stages_save(
        _make_post_request({"stages": {"NCT001": {"stage": "Watching"}}})
    )
    data = json.loads(response.body)
    assert response.status_code == 500
    assert "error" in data


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.set_agent_state",
    new_callable=AsyncMock,
)
async def test_funnel_stages_save_empty_is_valid(mock_set):
    """Empty dict is valid — clears all stage assignments."""
    mock_set.return_value = {}
    response = await api_funnel_stages_save(_make_post_request({"stages": {}}))
    data = json.loads(response.body)
    assert response.status_code == 200
    assert data["count"] == 0
