"""Tests for the Fact Timeline API endpoint (#328)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_facts


class FakeRequest:
    def __init__(self, query_params: dict | None = None):
        self.method = "GET"
        self.headers = {"origin": "https://dashboard.oncoteam.cloud"}
        self.query_params = query_params or {}


JOURNEY_ITEMS = [
    {
        "date": "2026-03-19",
        "type": "document",
        "subtype": "labs",
        "title": "Pre-C3 Labs CBC.pdf",
        "detail": "WBC 5.2, HGB 12.1",
        "id": 101,
    },
    {
        "date": "2026-03-17",
        "type": "conversation",
        "subtype": "autonomous_briefing",
        "title": "Weekly Research Briefing",
        "detail": "New trials for KRAS G12S...",
        "id": 201,
    },
    {
        "date": "2026-03-15",
        "type": "document",
        "subtype": "chemo_sheet",
        "title": "Chemo Sheet C3.pdf",
        "detail": "mFOLFOX6 cycle 3",
        "id": 102,
    },
    {
        "date": "2026-03-10",
        "type": "conversation",
        "subtype": "agent_run",
        "title": "Agent run: lab_sync | $0.15",
        "detail": '{"task_name": "lab_sync"}',
        "id": 202,
    },
]

TREATMENT_EVENTS = {
    "events": [
        {
            "id": 40,
            "event_date": "2026-03-19",
            "event_type": "chemotherapy",
            "title": "C3 — mFOLFOX6 Cycle 3",
            "notes": "Cycle 3 administered.",
            "tags": [],
        },
        {
            "id": 41,
            "event_date": "2026-03-18",
            "event_type": "lab_result",
            "title": "Pre-C3 Labs",
            "notes": "WBC 5.2, CEA 732",
            "tags": [],
        },
    ]
}


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_returns_merged_data(mock_journey, mock_events):
    """Facts endpoint merges journey timeline + treatment events."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest({"patient_id": "q1b"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] > 0
    assert data["has_more"] is False

    # Should have both document and treatment event items
    ids = [f["id"] for f in data["facts"]]
    assert "doc:101" in ids
    assert "te:40" in ids

    # Should be sorted newest first by default
    dates = [f["date"] for f in data["facts"]]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_category_filter(mock_journey, mock_events):
    """Category filter limits results to specified categories."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest({"patient_id": "q1b", "categories": "clinical"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    for fact in data["facts"]:
        assert fact["category"] == "clinical"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_search_filter(mock_journey, mock_events):
    """Search filters facts by title/summary substring match."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest({"patient_id": "q1b", "search": "KRAS"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert "KRAS" in data["facts"][0]["summary"]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_pagination(mock_journey, mock_events):
    """Pagination returns correct slice with has_more flag."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    # Request first 2 items
    request = FakeRequest({"patient_id": "q1b", "limit": "2", "offset": "0"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["facts"]) == 2
    assert data["has_more"] is True
    assert data["total"] == 6  # 4 journey + 2 treatment

    # Request next page
    request2 = FakeRequest({"patient_id": "q1b", "limit": "2", "offset": "2"})
    response2 = await api_facts(request2)
    data2 = json.loads(response2.body)

    assert len(data2["facts"]) == 2
    assert data2["has_more"] is True


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_date_range(mock_journey, mock_events):
    """Date range filtering works correctly."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest(
        {
            "patient_id": "q1b",
            "date_from": "2026-03-17",
            "date_to": "2026-03-18",
        }
    )
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    for fact in data["facts"]:
        assert "2026-03-17" <= fact["date"] <= "2026-03-18"


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_oldest_sort(mock_journey, mock_events):
    """Sort=oldest returns chronological order."""
    mock_journey.return_value = JOURNEY_ITEMS
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest({"patient_id": "q1b", "sort": "oldest"})
    response = await api_facts(request)
    data = json.loads(response.body)

    dates = [f["date"] for f in data["facts"]]
    assert dates == sorted(dates)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_contaminated_ids_excluded(mock_journey, mock_events):
    """Contaminated event IDs are filtered out."""
    mock_journey.return_value = []
    mock_events.return_value = {
        "events": [
            {
                "id": 19,
                "event_date": "2026-01-01",
                "event_type": "lab_result",
                "title": "Bad data",
                "notes": "",
            },
            {
                "id": 50,
                "event_date": "2026-01-02",
                "event_type": "lab_result",
                "title": "Good data",
                "notes": "",
            },
        ]
    }

    request = FakeRequest({"patient_id": "q1b"})
    response = await api_facts(request)
    data = json.loads(response.body)

    ids = [f["id"] for f in data["facts"]]
    assert "te:19" not in ids
    assert "te:50" in ids


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_journey_timeline",
    new_callable=AsyncMock,
)
async def test_facts_partial_failure_returns_available(mock_journey, mock_events):
    """If one source fails, the other source's data is still returned."""
    mock_journey.side_effect = ConnectionError("oncofiles down")
    mock_events.return_value = TREATMENT_EVENTS

    request = FakeRequest({"patient_id": "q1b"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2  # only treatment events
    assert all(f["id"].startswith("te:") for f in data["facts"])


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "open", "failures": 5},
)
async def test_facts_circuit_breaker(mock_cb):
    """Returns 503 when circuit breaker is open."""
    request = FakeRequest({"patient_id": "q1b"})
    response = await api_facts(request)
    data = json.loads(response.body)

    assert response.status_code == 503
    assert data["facts"] == []
