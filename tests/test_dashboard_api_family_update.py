"""Tests for /api/family-update dashboard endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import _translate_for_family, api_family_update


class FakeRequest:
    def __init__(self, method: str = "GET", query: str = "patient_id=q1b", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams(query)
        self._body = body

    async def body(self) -> bytes:
        return self._body


MOCK_FAMILY_UPDATES = [
    {
        "id": 1,
        "title": "Týždenná správa pre rodinu",
        "content": "Liečba prebieha — cyklus 2.",
        "created_at": "2026-03-07",
        "tags": ["lang:sk"],
    },
]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.search_conversations",
    new_callable=AsyncMock,
)
async def test_api_family_update_get_returns_entries(mock_search):
    mock_search.return_value = MOCK_FAMILY_UPDATES
    request = FakeRequest("GET")
    response = await api_family_update(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["updates"][0]["title"] == "Týždenná správa pre rodinu"
    mock_search.assert_called_once_with(entry_type="family_update", limit=20, token=None)


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.search_conversations",
    new_callable=AsyncMock,
)
async def test_api_family_update_get_handles_error(mock_search):
    mock_search.side_effect = Exception("fail")
    request = FakeRequest("GET")
    response = await api_family_update(request)
    assert response.status_code == 502


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.log_conversation",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_family_update_post_generates_sk(mock_list, mock_log):
    mock_list.return_value = []
    mock_log.return_value = {"id": 1}
    body = json.dumps({"lang": "sk"}).encode()
    request = FakeRequest("POST", body=body)
    response = await api_family_update(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["created"] is True
    assert data["lang"] == "sk"
    assert "cyklus" in data["content"].lower()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.log_conversation",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_family_update_post_generates_en(mock_list, mock_log):
    mock_list.return_value = []
    mock_log.return_value = {"id": 1}
    request = FakeRequest("POST", query="patient_id=q1b&lang=en", body=b"{}")
    response = await api_family_update(request)
    data = json.loads(response.body)

    assert data["created"] is True
    assert data["lang"] == "en"
    assert "cycle" in data["content"].lower()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.log_conversation",
    new_callable=AsyncMock,
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_treatment_events",
    new_callable=AsyncMock,
)
async def test_api_family_update_post_handles_empty_data(mock_list, mock_log):
    mock_list.return_value = []
    mock_log.return_value = {"id": 1}
    request = FakeRequest("POST", body=b"")
    response = await api_family_update(request)
    data = json.loads(response.body)

    assert data["created"] is True
    assert len(data["content"]) > 0


# ── _translate_for_family unit tests ──────────


def test_translate_safe_labs_sk():
    content = _translate_for_family(
        labs={"ANC": 2100},
        toxicity=None,
        milestones=[],
        weight_data={"baseline_weight_kg": 72, "alerts": []},
        lang="sk",
    )
    assert "bezpečnom rozsahu" in content
    assert "stabilná" in content


def test_translate_low_counts_sk():
    content = _translate_for_family(
        labs={"ANC": 800},
        toxicity=None,
        milestones=[],
        weight_data=None,
        lang="sk",
    )
    assert "nižšie" in content


def test_translate_high_toxicity_sk():
    content = _translate_for_family(
        labs=None,
        toxicity={"neuropathy": 1, "fatigue": 3},
        milestones=[],
        weight_data=None,
        lang="sk",
    )
    assert "brnenie" in content
    assert "únava" in content.lower()
