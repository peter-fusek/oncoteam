"""Tests for /api/toxicity and /api/labs dashboard endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_labs, api_toxicity


class FakeRequest:
    """Minimal Starlette Request stub with method and body support."""

    def __init__(self, method: str = "GET", query: str = "", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


# ── /api/toxicity GET ────────────────────────────


MOCK_TOXICITY_EVENTS = [
    {
        "id": 1,
        "event_date": "2026-03-01",
        "event_type": "toxicity_log",
        "title": "Toxicity log 2026-03-01",
        "notes": "Mild neuropathy in fingers",
        "metadata": {"neuropathy": 1, "fatigue": 2, "weight_kg": 65},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_toxicity_get_returns_entries(mock_list):
    mock_list.return_value = MOCK_TOXICITY_EVENTS
    request = FakeRequest("GET")
    response = await api_toxicity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["entries"][0]["date"] == "2026-03-01"
    assert data["entries"][0]["metadata"]["neuropathy"] == 1
    mock_list.assert_called_once_with(event_type="toxicity_log", limit=50)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_toxicity_get_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_toxicity(request)
    assert response.status_code == 502


# ── /api/toxicity POST ───────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_toxicity_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 99}
    body = json.dumps(
        {
            "date": "2026-03-07",
            "neuropathy": 1,
            "fatigue": 2,
            "notes": "Tingling in toes",
        }
    ).encode()
    request = FakeRequest("POST", body=body)
    response = await api_toxicity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    mock_add.assert_called_once()
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_date"] == "2026-03-07"
    assert call_kwargs["event_type"] == "toxicity_log"
    assert call_kwargs["metadata"]["neuropathy"] == 1
    assert call_kwargs["metadata"]["fatigue"] == 2


@pytest.mark.anyio
async def test_api_toxicity_post_requires_date():
    body = json.dumps({"neuropathy": 1}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_toxicity(request)
    assert response.status_code == 400


@pytest.mark.anyio
async def test_api_toxicity_post_rejects_invalid_json():
    request = FakeRequest("POST", body=b"not json")
    response = await api_toxicity(request)
    assert response.status_code == 400


# ── /api/labs GET ────────────────────────────────


MOCK_LAB_EVENTS = [
    {
        "id": 10,
        "event_date": "2026-03-01",
        "event_type": "lab_result",
        "title": "Lab results 2026-03-01",
        "notes": "",
        "metadata": {"ANC": 2100, "PLT": 180000, "CEA": 12.5, "CA_19_9": 45.0},
    },
    {
        "id": 11,
        "event_date": "2026-02-15",
        "event_type": "lab_result",
        "title": "Lab results 2026-02-15",
        "notes": "Low platelets",
        "metadata": {"ANC": 800, "PLT": 60000},
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_get_returns_entries_with_alerts(mock_list):
    mock_list.return_value = MOCK_LAB_EVENTS
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2

    # First entry: all values safe
    assert data["entries"][0]["values"]["CEA"] == 12.5
    assert data["entries"][0]["alerts"] == []

    # Second entry: ANC < 1500 and PLT < 75000 -> 2 alerts
    assert len(data["entries"][1]["alerts"]) == 2
    alert_params = [a["param"] for a in data["entries"][1]["alerts"]]
    assert "ANC" in alert_params
    assert "PLT" in alert_params


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_labs_get_handles_string_metadata(mock_list):
    """Metadata may come as JSON string from oncofiles."""
    mock_list.return_value = [
        {
            "id": 1,
            "event_date": "2026-03-01",
            "event_type": "lab_result",
            "title": "Lab",
            "notes": "",
            "metadata": '{"ANC": 2000, "PLT": 100000}',
        }
    ]
    request = FakeRequest("GET")
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["entries"][0]["values"]["ANC"] == 2000
    assert data["entries"][0]["alerts"] == []


# ── /api/labs POST ───────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.add_treatment_event",
    new_callable=AsyncMock,
)
async def test_api_labs_post_creates_entry(mock_add):
    mock_add.return_value = {"id": 20}
    body = json.dumps(
        {
            "date": "2026-03-07",
            "values": {"ANC": 2500, "PLT": 160000, "CEA": 10.2},
            "notes": "Pre-cycle labs",
        }
    ).encode()
    request = FakeRequest("POST", body=body)
    response = await api_labs(request)
    data = json.loads(response.body)

    assert data["created"] is True
    call_kwargs = mock_add.call_args[1]
    assert call_kwargs["event_type"] == "lab_result"
    assert call_kwargs["metadata"]["ANC"] == 2500


@pytest.mark.anyio
async def test_api_labs_post_requires_date():
    body = json.dumps({"values": {"ANC": 2000}}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_labs(request)
    assert response.status_code == 400
