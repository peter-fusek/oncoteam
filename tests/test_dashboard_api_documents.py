"""Tests for /api/documents endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_documents


def _make_request(query_string: str = "patient_id=q1b") -> object:
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
                "has_ocr": True,
                "has_ai": True,
                "has_metadata": True,
                "fully_complete": True,
                "is_synced": True,
            },
            {
                "id": 2,
                "filename": "scan.pdf",
                "category": "imaging",
                "has_ocr": False,
                "has_ai": False,
                "has_metadata": False,
                "fully_complete": False,
                "is_synced": True,
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
    mock_call.assert_called_once_with(
        "get_document_status_matrix", {"filter": "all", "limit": 500}, token=None
    )


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_with_filter(mock_call):
    mock_call.return_value = {"documents": []}

    request = _make_request("patient_id=q1b&filter=missing_ocr")
    response = await api_documents(request)
    data = json.loads(response.body)

    assert data["filter"] == "missing_ocr"
    mock_call.assert_called_once_with(
        "get_document_status_matrix", {"filter": "missing_ocr", "limit": 500}, token=None
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


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
async def test_documents_returns_all_docs_when_patient_has_over_100(mock_call):
    """#378 regression: q1b had 109 docs in oncofiles but the dashboard showed
    100 because the default limit silently truncated the archive. The status-
    matrix mode must request at least 500 and surface the full count.
    """
    mock_call.return_value = {
        "documents": [
            {
                "id": i,
                "filename": f"doc_{i}.pdf",
                "has_ocr": True,
                "has_ai": True,
                "has_metadata": True,
            }
            for i in range(109)
        ]
    }

    request = _make_request()
    response = await api_documents(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 109
    assert len(data["documents"]) == 109
    # The call must have requested ≥500 so oncofiles doesn't cap the archive.
    args, kwargs = mock_call.call_args
    assert args[1]["limit"] >= 500


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_documents", new_callable=AsyncMock)
async def test_documents_category_routes_to_search(mock_search):
    """?category=genetics must call search_documents, not get_document_status_matrix,
    and return full envelopes (ai_summary, structured_metadata, gdrive_url)."""
    mock_search.return_value = {
        "documents": [
            {
                "id": 169,
                "filename": "20260415_genetics.jpg",
                "document_date": "2026-04-15",
                "category": "genetics",
                "gdrive_url": "https://drive.google.com/file/d/abc/view",
                "ai_summary": "Hereditary panel: no pathogenic mutations identified",
                "structured_metadata": {
                    "findings": ["BRCA1/BRCA2 tested", "No variants"],
                    "doctors": ["Dr. Test"],
                },
            }
        ]
    }

    request = _make_request("patient_id=q1b&category=genetics&limit=5")
    response = await api_documents(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["category"] == "genetics"
    assert data["total"] == 1
    assert data["documents"][0]["ai_summary"].startswith("Hereditary panel")
    assert data["documents"][0]["gdrive_url"].startswith("https://drive.google.com/")
    mock_search.assert_called_once_with(text="", category="genetics", limit=5, token=None)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.call_oncofiles", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api.oncofiles_client.search_documents", new_callable=AsyncMock)
async def test_documents_category_does_not_call_status_matrix(mock_search, mock_call):
    """When ?category= is provided, the status-matrix path must NOT be invoked."""
    mock_search.return_value = {"documents": []}

    request = _make_request("patient_id=q1b&category=pathology")
    await api_documents(request)

    mock_search.assert_called_once()
    mock_call.assert_not_called()
