"""Tests for /api/detail/{type}/{id} dashboard endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_detail


class FakeRequest:
    """Minimal Starlette Request stub with path_params."""

    def __init__(self, path_params: dict, query: str = ""):
        from starlette.datastructures import QueryParams

        self.method = "GET"
        self.path_params = path_params
        self.query_params = QueryParams(query)


# ── treatment_event ────────────────────────────


MOCK_EVENT = {
    "id": 5,
    "event_date": "2026-03-01",
    "event_type": "chemo_cycle",
    "title": "C3 mFOLFOX6",
    "notes": "Day 1 infusion",
    "metadata": '{"dose_percent": 100}',
}


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_treatment_event",
    new_callable=AsyncMock,
)
async def test_detail_treatment_event(mock_get):
    mock_get.return_value = MOCK_EVENT.copy()
    req = FakeRequest({"type": "treatment_event", "id": "5"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["type"] == "treatment_event"
    assert body["id"] == "5"
    assert body["data"]["title"] == "C3 mFOLFOX6"
    assert body["data"]["metadata"] == {"dose_percent": 100}
    assert body["source"]["oncofiles_id"] == 5
    mock_get.assert_awaited_once_with(5)


# ── research ────────────────────────────


MOCK_RESEARCH = {
    "id": 12,
    "source": "pubmed",
    "external_id": "39876543",
    "title": "KRAS G12S sensitivity study",
    "summary": "Novel findings...",
}


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_research_entry",
    new_callable=AsyncMock,
)
async def test_detail_research_with_pubmed_link(mock_get):
    mock_get.return_value = MOCK_RESEARCH.copy()
    req = FakeRequest({"type": "research", "id": "12"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["type"] == "research"
    assert body["data"]["external_url"] == "https://pubmed.ncbi.nlm.nih.gov/39876543/"
    assert body["source"]["oncofiles_id"] == 12


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_research_entry",
    new_callable=AsyncMock,
    side_effect=Exception("not implemented"),
)
@patch(
    "oncoteam.dashboard_api.oncofiles_client.list_research_entries",
    new_callable=AsyncMock,
)
async def test_detail_research_fallback(mock_list, mock_get):
    mock_list.return_value = [MOCK_RESEARCH.copy()]
    req = FakeRequest({"type": "research", "id": "12"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["data"]["title"] == "KRAS G12S sensitivity study"


# ── biomarker (static) ────────────────────────────


@pytest.mark.anyio
async def test_detail_biomarker_static():
    req = FakeRequest({"type": "biomarker", "id": "KRAS"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["type"] == "biomarker"
    assert body["data"]["name"] == "KRAS"
    assert "mutant" in body["data"]["value"].lower() or "G12S" in body["data"]["value"]


# ── protocol_section (static) ────────────────────────────


@pytest.mark.anyio
async def test_detail_protocol_section():
    req = FakeRequest({"type": "protocol_section", "id": "lab_thresholds"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["type"] == "protocol_section"
    assert body["data"]["section"] == "lab_thresholds"
    assert isinstance(body["data"]["data"], dict)
    assert "ANC" in body["data"]["data"]


# ── unknown type ────────────────────────────


@pytest.mark.anyio
async def test_detail_unknown_type():
    req = FakeRequest({"type": "unknown", "id": "1"})
    resp = await api_detail(req)
    assert resp.status_code == 400


# ── patient (static) ────────────────────────────


@pytest.mark.anyio
async def test_detail_patient():
    req = FakeRequest({"type": "patient", "id": "0"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["type"] == "patient"
    assert "name" in body["data"]


# ── document ────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_document",
    new_callable=AsyncMock,
)
async def test_detail_document_with_gdrive(mock_get):
    mock_get.return_value = {
        "id": 7,
        "filename": "lab_report.pdf",
        "gdrive_file_id": "abc123",
        "content": "Lab results...",
    }
    req = FakeRequest({"type": "document", "id": "7"})
    resp = await api_detail(req)
    import json

    body = json.loads(resp.body)
    assert body["source"]["gdrive_file_id"] == "abc123"
    assert body["source"]["gdrive_url"] == "https://drive.google.com/file/d/abc123/view"
