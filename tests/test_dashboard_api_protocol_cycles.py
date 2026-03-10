"""Tests for /api/protocol/cycles endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_protocol_cycles


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)

    return FakeRequest(query_string)


MOCK_CHEMO_EVENTS = [
    {
        "id": 1,
        "title": "mFOLFOX6 C1",
        "event_date": "2026-02-15",
        "event_type": "chemotherapy",
    },
    {
        "id": 2,
        "title": "mFOLFOX6 C2",
        "event_date": "2026-03-01",
        "event_type": "chemotherapy",
    },
]

MOCK_LAB_EVENTS = [
    {
        "id": 10,
        "title": "Lab results C1",
        "event_date": "2026-02-14",
        "event_type": "lab_result",
        "data": {
            "ANC": 3200,
            "PLT": 185000,
            "creatinine": 0.8,
            "ALT": 25,
            "bilirubin": 0.9,
        },
    },
    {
        "id": 11,
        "title": "Lab results C2",
        "event_date": "2026-02-28",
        "event_type": "lab_result",
        "data": {
            "ANC": 1200,
            "PLT": 60000,
            "creatinine": 0.9,
            "ALT": 30,
        },
    },
]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_returns_cycles(mock_list):
    """Should return cycle history with lab evaluations."""
    mock_list.side_effect = [
        {"entries": MOCK_LAB_EVENTS},
        {"entries": MOCK_CHEMO_EVENTS},
    ]
    request = _make_request()
    response = await api_protocol_cycles(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "cycles" in data
    assert "current_cycle" in data
    assert data["current_cycle"] == 3
    assert len(data["cycles"]) == 2  # cycles 1 and 2


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_lab_evaluation_pass(mock_list):
    """Cycle 1 labs should all pass thresholds."""
    mock_list.side_effect = [
        {"entries": MOCK_LAB_EVENTS},
        {"entries": MOCK_CHEMO_EVENTS},
    ]
    request = _make_request()
    response = await api_protocol_cycles(request)
    data = json.loads(response.body)

    cycle1 = data["cycles"][0]
    assert cycle1["cycle_number"] == 1
    assert cycle1["overall_pass"] is True
    assert "ANC" in cycle1["lab_evaluation"]
    assert cycle1["lab_evaluation"]["ANC"]["pass"] is True
    assert cycle1["lab_evaluation"]["ANC"]["value"] == 3200


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_lab_evaluation_fail(mock_list):
    """Cycle 2 labs should fail (ANC < 1500, PLT < 75000)."""
    mock_list.side_effect = [
        {"entries": MOCK_LAB_EVENTS},
        {"entries": MOCK_CHEMO_EVENTS},
    ]
    request = _make_request()
    response = await api_protocol_cycles(request)
    data = json.loads(response.body)

    cycle2 = data["cycles"][1]
    assert cycle2["cycle_number"] == 2
    assert cycle2["overall_pass"] is False
    assert cycle2["lab_evaluation"]["ANC"]["pass"] is False
    assert cycle2["lab_evaluation"]["PLT"]["pass"] is False


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_no_data(mock_list):
    """Should return empty cycles gracefully when no data."""
    mock_list.side_effect = [
        {"entries": []},
        {"entries": []},
    ]
    request = _make_request()
    response = await api_protocol_cycles(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["cycles"]) == 2  # still lists cycles 1,2 (no lab data)
    assert data["cycles"][0]["lab_evaluation"] == {}
    assert data["cycles"][0]["overall_pass"] is True  # no labs = vacuously true


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_has_cors(mock_list):
    mock_list.side_effect = [{"entries": []}, {"entries": []}]
    request = _make_request()
    response = await api_protocol_cycles(request)
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_cycles_handles_error(mock_list):
    """Should return empty cycles on oncofiles error."""
    mock_list.side_effect = Exception("connection refused")
    request = _make_request()
    response = await api_protocol_cycles(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["cycles"] == []
    assert "error" in data
