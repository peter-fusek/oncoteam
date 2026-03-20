"""Tests for document pipeline: webhook + orchestrator + single-doc agents."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.agent_registry import AGENT_REGISTRY
from oncoteam.autonomous_tasks import (
    _classify_doc_type,
    run_document_pipeline,
)

# ── Agent registry ─────────────────────────────


def test_pipeline_agent_in_registry():
    """document_pipeline must appear in the agent registry."""
    assert "document_pipeline" in AGENT_REGISTRY
    agent = AGENT_REGISTRY["document_pipeline"]
    assert agent.category.value == "data_pipeline"
    assert agent.cooldown_hours == 0
    assert agent.model == "light"


# ── Classification ─────────────────────────────


@pytest.mark.parametrize(
    "response,metadata,expected",
    [
        ("This is a lab report with blood counts", {}, "lab_report"),
        ("Krvný obraz from hospital", {}, "lab_report"),
        ("", {"category": "lab"}, "lab_report"),
        ("", {"category": "labs"}, "lab_report"),
        ("Visit note from oncologist", {}, "visit_note"),
        ("Konzultacia u onkológa", {}, "visit_note"),
        ("Discharge summary / prepustenie", {}, "discharge_summary"),
        ("Pathology report", {}, "pathology"),
        ("Genetics panel results", {}, "genetics"),
        ("CT scan imaging report", {}, "imaging"),
        ("Some random document", {}, "other"),
        # Metadata category takes precedence
        ("This looks like a visit note", {"category": "pathology"}, "pathology"),
    ],
)
def test_classify_doc_type(response, metadata, expected):
    assert _classify_doc_type(response, metadata) == expected


# ── Pipeline orchestrator ──────────────────────


@pytest.mark.anyio
async def test_pipeline_deduplication():
    """Second call for same document_id should return early."""
    with patch(
        "oncoteam.autonomous_tasks._get_state",
        AsyncMock(return_value={"timestamp": "2026-03-20T10:00:00+00:00"}),
    ):
        result = await run_document_pipeline(42)
    assert result["skipped"] is True
    assert result["reason"] == "already_processed"


@pytest.mark.anyio
async def test_pipeline_dispatches_lab():
    """Lab report classification triggers lab_sync_single downstream."""
    mock_scan = AsyncMock(return_value={
        "response": "This is a lab report with blood values",
        "cost": 0.01,
        "tool_calls": [{"name": "view_document"}],
        "error": None,
        "model": "haiku",
        "duration_ms": 500,
    })
    mock_lab = AsyncMock(return_value={
        "response": "Extracted WBC, ANC",
        "cost": 0.005,
        "tool_calls": [],
        "error": None,
        "model": "haiku",
        "duration_ms": 300,
    })

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_lab_sync_single", mock_lab),
        patch("oncoteam.autonomous_tasks._send_whatsapp", AsyncMock()),
    ):
        result = await run_document_pipeline(100, {"category": ""})

    assert result["doc_type"] == "lab_report"
    assert result["document_id"] == 100
    assert len(result["steps"]) == 2
    assert result["steps"][0]["step"] == "file_scan"
    assert result["steps"][1]["step"] == "lab_sync"
    assert result["cost"] == pytest.approx(0.015)


@pytest.mark.anyio
async def test_pipeline_dispatches_visit_note():
    """Visit note triggers both toxicity_extraction and weight_extraction."""
    mock_scan = AsyncMock(return_value={
        "response": "Konzultacia u onkológa, vizita note",
        "cost": 0.01,
        "tool_calls": [],
        "error": None,
        "model": "haiku",
        "duration_ms": 500,
    })
    mock_tox = AsyncMock(return_value={
        "response": "Neuropathy grade 1",
        "cost": 0.005,
        "tool_calls": [],
        "error": None,
    })
    mock_weight = AsyncMock(return_value={
        "response": "Weight 68kg",
        "cost": 0.003,
        "tool_calls": [],
        "error": None,
    })

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_toxicity_extraction_single", mock_tox),
        patch("oncoteam.autonomous_tasks.run_weight_extraction_single", mock_weight),
    ):
        result = await run_document_pipeline(200)

    assert result["doc_type"] == "visit_note"
    assert len(result["steps"]) == 3
    step_names = [s["step"] for s in result["steps"]]
    assert step_names == ["file_scan", "toxicity_extraction", "weight_extraction"]


@pytest.mark.anyio
async def test_pipeline_error_handling():
    """If file_scan fails, no downstream agents should run."""
    mock_scan = AsyncMock(side_effect=RuntimeError("API down"))

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
    ):
        result = await run_document_pipeline(300)

    assert result["error"] is not None
    assert "file_scan_single failed" in result["error"]
    # Only the file_scan step should appear (no downstream)
    assert len(result["steps"]) == 1
    assert result["steps"][0]["step"] == "file_scan"


# ── Webhook endpoint ───────────────────────────


def _make_request(body: dict, headers: dict | None = None):
    """Create a mock Starlette Request with JSON body."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/internal/document-webhook",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in (headers or {}).items()
        ],
    }

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    return Request(scope, receive)


@pytest.mark.anyio
async def test_webhook_rejects_no_auth():
    """Webhook should reject requests without API key."""

    request = _make_request({"document_id": 1})
    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", "secret"),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "streamable-http"),
    ):
        from oncoteam.dashboard_api import _check_api_auth

        err = _check_api_auth(request)
    assert err is not None
    data = json.loads(err.body)
    assert "error" in data


@pytest.mark.anyio
async def test_webhook_rejects_invalid_body():
    """Webhook should reject missing or invalid document_id."""
    from oncoteam.dashboard_api import api_document_webhook

    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
    ):
        # Missing document_id
        request = _make_request({"filename": "test.pdf"})
        resp = await api_document_webhook(request)
        data = json.loads(resp.body)
        assert data["error"] == "document_id must be a positive integer"

        # Invalid document_id
        request = _make_request({"document_id": -5})
        resp = await api_document_webhook(request)
        data = json.loads(resp.body)
        assert data["error"] == "document_id must be a positive integer"


@pytest.mark.anyio
async def test_webhook_starts_pipeline():
    """Valid webhook call should return pipeline_started."""
    from oncoteam.dashboard_api import api_document_webhook

    request = _make_request({"document_id": 42, "category": "lab"})
    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        patch(
            "oncoteam.autonomous_tasks._get_state",
            AsyncMock(return_value={}),
        ),
        patch(
            "oncoteam.autonomous_tasks._extract_timestamp",
            return_value="",
        ),
        patch(
            "oncoteam.autonomous_tasks.run_document_pipeline",
            AsyncMock(return_value={"ok": True}),
        ),
    ):
        resp = await api_document_webhook(request)
    data = json.loads(resp.body)
    assert data["status"] == "pipeline_started"
    assert data["document_id"] == 42


@pytest.mark.anyio
async def test_webhook_deduplication():
    """Webhook should return already_processed for duplicate document_id."""
    from oncoteam.dashboard_api import api_document_webhook

    request = _make_request({"document_id": 42})
    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        patch(
            "oncoteam.autonomous_tasks._get_state",
            AsyncMock(return_value={"timestamp": "2026-03-20T10:00:00+00:00"}),
        ),
        patch(
            "oncoteam.autonomous_tasks._extract_timestamp",
            return_value="2026-03-20T10:00:00+00:00",
        ),
    ):
        resp = await api_document_webhook(request)
    data = json.loads(resp.body)
    assert data["status"] == "already_processed"
