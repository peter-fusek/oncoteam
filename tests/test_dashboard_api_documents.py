"""Tests for /api/documents endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_documents


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_returns_list(mock_call):
    mock_call.return_value = {
        "documents": [
            {
                "id": 1,
                "filename": "lab-2026-03-01.pdf",
                "category": "labs",
                "ocr_status": "complete",
                "metadata_status": "complete",
                "ai_summary_status": "complete",
                "tags": ["labs"],
                "updated_at": "2026-03-01T10:00:00Z",
            },
            {
                "id": 2,
                "filename": "scan.pdf",
                "category": "imaging",
                "ocr_status": "missing",
                "metadata_status": "incomplete",
                "ai_summary_status": None,
                "tags": [],
                "updated_at": None,
            },
        ]
    }

    request = _make_request()
    response = await api_documents(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2
    assert data["filter"] == "all"
    assert data["summary"]["total"] == 2
    assert data["summary"]["ocr_complete"] == 1
    assert data["summary"]["missing_ocr"] == 1
    assert data["summary"]["missing_metadata"] == 1
    mock_call.assert_called_once_with("get_document_status_matrix", {"filter": "all"}, token=None)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_with_filter(mock_call):
    mock_call.return_value = {"documents": []}

    request = _make_request("filter=missing_ocr")
    response = await api_documents(request)
    data = json.loads(response.body)

    assert data["filter"] == "missing_ocr"
    mock_call.assert_called_once_with(
        "get_document_status_matrix", {"filter": "missing_ocr"}, token=None
    )


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_handles_list_response(mock_call):
    """Oncofiles may return a plain list instead of {documents: [...]}."""
    mock_call.return_value = [
        {"id": 1, "filename": "a.pdf", "ocr_status": "complete", "metadata_status": "complete"},
    ]

    request = _make_request()
    response = await api_documents(request)
    data = json.loads(response.body)

    assert data["total"] == 1
    assert len(data["documents"]) == 1


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_error(mock_call):
    mock_call.side_effect = Exception("connection refused")

    request = _make_request()
    response = await api_documents(request)
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "error" in data
    assert data["total"] == 0
    assert data["summary"]["total"] == 0
