"""Tests for /api/medications dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_medications


class FakeRequest:
    def __init__(self, method: str = "GET", query: str = "", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


MOCK_MEDICATION_EVENTS = [
    {
        "id": 1,
        "event_date": "2026-03-07",
        "event_type": "medication_log",
        "title": "Clexane 2026-03-07",
        "notes": "Morning dose",
        "metadata": {
            "name": "Clexane",
            "dose": "0.6ml SC",
            "frequency": "2x/day",
            "active": True,
        },
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_returns_entries(mock_list):
    mock_list.return_value = MOCK_MEDICATION_EVENTS
    request = FakeRequest("GET")
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["medications"][0]["name"] == "Clexane"
    assert data["medications"][0]["dose"] == "0.6ml SC"
    mock_list.assert_called_once_with(event_type="medication_log", limit=50)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_includes_defaults(mock_list):
    mock_list.return_value = []
    request = FakeRequest("GET")
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["default_medications"]) == 4
    names = [m["name"] for m in data["default_medications"]]
    assert "Clexane" in names
    assert "Ondansetron" in names


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_medications_get_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_medications(request)
    assert response.status_code == 502
    data = json.loads(response.body)
    assert len(data["default_medications"]) == 4


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_medications_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 99}
    body = json.dumps({"date": "2026-03-07", "name": "Clexane", "dose": "0.6ml SC"}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_type"] == "medication_log"
    assert call_kwargs["metadata"]["name"] == "Clexane"


@pytest.mark.anyio
async def test_api_medications_post_requires_date_and_name():
    body = json.dumps({"name": "Clexane"}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_medications(request)
    assert response.status_code == 400

    body2 = json.dumps({"date": "2026-03-07"}).encode()
    request2 = FakeRequest("POST", body=body2)
    response2 = await api_medications(request2)
    assert response2.status_code == 400


@pytest.mark.anyio
async def test_api_medications_post_rejects_invalid_json():
    request = FakeRequest("POST", body=b"not json")
    response = await api_medications(request)
    assert response.status_code == 400
