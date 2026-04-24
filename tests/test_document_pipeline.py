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
        # Chemo sheet classification
        ("", {"category": "chemo_sheet"}, "chemo_sheet"),
        ("", {"category": "chemo"}, "chemo_sheet"),
        ("Chemoterapia mFOLFOX6 cyklus 2", {}, "chemo_sheet"),
        ("Oxaliplatina 85 mg/m2 infusion", {}, "chemo_sheet"),
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
    mock_scan = AsyncMock(
        return_value={
            "response": "This is a lab report with blood values",
            "cost": 0.01,
            "tool_calls": [{"name": "view_document"}],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_lab = AsyncMock(
        return_value={
            "response": "Extracted WBC, ANC",
            "cost": 0.005,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 300,
        }
    )

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
    """Visit note triggers lab_sync (#426 inline-labs scan) + toxicity +
    weight extraction. Slovak oncology visit notes routinely quote
    pre-visit bloods inline."""
    mock_scan = AsyncMock(
        return_value={
            "response": "Konzultacia u onkológa, vizita note",
            "cost": 0.01,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_lab = AsyncMock(
        return_value={
            "response": "Extracted inline WBC=12.11, ANC=1150",
            "cost": 0.002,
            "tool_calls": [],
            "error": None,
        }
    )
    mock_tox = AsyncMock(
        return_value={
            "response": "Neuropathy grade 1",
            "cost": 0.005,
            "tool_calls": [],
            "error": None,
        }
    )
    mock_weight = AsyncMock(
        return_value={
            "response": "Weight 68kg",
            "cost": 0.003,
            "tool_calls": [],
            "error": None,
        }
    )

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_lab_sync_single", mock_lab),
        patch("oncoteam.autonomous_tasks.run_toxicity_extraction_single", mock_tox),
        patch("oncoteam.autonomous_tasks.run_weight_extraction_single", mock_weight),
    ):
        result = await run_document_pipeline(200)

    assert result["doc_type"] == "visit_note"
    assert len(result["steps"]) == 4
    step_names = [s["step"] for s in result["steps"]]
    assert step_names == ["file_scan", "lab_sync", "toxicity_extraction", "weight_extraction"]


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


@pytest.mark.anyio
async def test_pipeline_dispatches_chemo_sheet():
    """Chemo sheet classification triggers dose_extraction_single downstream."""
    mock_scan = AsyncMock(
        return_value={
            "response": "Chemoterapia mFOLFOX6 oxaliplatina 130mg",
            "cost": 0.01,
            "tool_calls": [{"name": "view_document"}],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_dose = AsyncMock(
        return_value={
            "response": "Extracted oxaliplatin 85mg/m2",
            "cost": 0.005,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 400,
        }
    )
    # #426: chemo sheets also get lab_sync (inline pre-chemo bloods)
    mock_lab = AsyncMock(
        return_value={
            "response": "Extracted pre-chemo WBC=4.2, ANC=2100",
            "cost": 0.002,
            "tool_calls": [],
            "error": None,
        }
    )

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_lab_sync_single", mock_lab),
        patch("oncoteam.autonomous_tasks.run_dose_extraction_single", mock_dose),
        patch("oncoteam.autonomous_tasks._send_whatsapp", AsyncMock()),
    ):
        result = await run_document_pipeline(400, {"category": "chemo_sheet"})

    assert result["doc_type"] == "chemo_sheet"
    assert result["document_id"] == 400
    assert len(result["steps"]) == 3
    step_names = [s["step"] for s in result["steps"]]
    assert step_names == ["file_scan", "lab_sync", "dose_extraction"]
    assert result["cost"] == pytest.approx(0.017)


@pytest.mark.anyio
async def test_pipeline_dispatches_discharge_summary_to_lab_sync():
    """#426 — discharge summaries routinely carry inline pre/post-admission
    bloods; pipeline must dispatch lab_sync_single even though the primary
    downstream is toxicity + weight extraction."""
    mock_scan = AsyncMock(
        return_value={
            "response": "Prepustaci suhrn, discharge summary — hospitalizacia",
            "cost": 0.01,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_lab = AsyncMock(
        return_value={
            "response": "Extracted inline HGB=108, PLT=195000",
            "cost": 0.002,
            "tool_calls": [],
            "error": None,
        }
    )
    mock_tox = AsyncMock(return_value={"response": "", "cost": 0.001, "error": None})
    mock_weight = AsyncMock(return_value={"response": "", "cost": 0.001, "error": None})

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_lab_sync_single", mock_lab),
        patch("oncoteam.autonomous_tasks.run_toxicity_extraction_single", mock_tox),
        patch("oncoteam.autonomous_tasks.run_weight_extraction_single", mock_weight),
    ):
        result = await run_document_pipeline(500)

    assert result["doc_type"] == "discharge_summary"
    step_names = [s["step"] for s in result["steps"]]
    assert "lab_sync" in step_names
    mock_lab.assert_called_once()


@pytest.mark.anyio
async def test_pipeline_dispatches_pathology_to_oncopanel_extraction():
    """#398 Phase 3b — pathology docs trigger structured oncopanel extraction."""
    mock_scan = AsyncMock(
        return_value={
            "response": "Molekulárna patológia, somatický oncopanel",
            "cost": 0.01,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_oncopanel = AsyncMock(
        return_value={
            "response": '```json\n{"panel_id": "test_p", "variants": [{"gene": "KRAS"}]}\n```',
            "cost": 0.015,
            "tool_calls": [{"name": "view_document"}],
            "error": None,
            "model": "sonnet",
        }
    )

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()) as mock_set,
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_oncopanel_extraction_single", mock_oncopanel),
    ):
        result = await run_document_pipeline(600, {"category": "pathology"})

    assert result["doc_type"] == "pathology"
    step_names = [s["step"] for s in result["steps"]]
    assert "oncopanel_extraction" in step_names
    mock_oncopanel.assert_called_once()
    # Dedup state is always set (line 1301); the pending_oncopanel persistence
    # happens inside run_oncopanel_extraction_single which is mocked here, so
    # we only verify dispatch occurred. Full extraction-persist coverage is in
    # test_oncopanel_extraction_persists_pending below.
    assert mock_set.called


@pytest.mark.anyio
async def test_pipeline_dispatches_genetics_to_oncopanel_extraction():
    """#398 Phase 3b — genetics docs route to the same extractor."""
    mock_scan = AsyncMock(
        return_value={
            "response": "Genetický panel — NGS TruSight-500",
            "cost": 0.01,
            "tool_calls": [],
            "error": None,
            "model": "haiku",
            "duration_ms": 500,
        }
    )
    mock_oncopanel = AsyncMock(
        return_value={"response": "```json\n{}\n```", "cost": 0.015, "error": None}
    )

    with (
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock()),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock()),
        patch("oncoteam.autonomous_tasks.run_file_scan_single", mock_scan),
        patch("oncoteam.autonomous_tasks.run_oncopanel_extraction_single", mock_oncopanel),
    ):
        result = await run_document_pipeline(601, {"category": "genetics"})

    assert result["doc_type"] == "genetics"
    step_names = [s["step"] for s in result["steps"]]
    assert "oncopanel_extraction" in step_names
    mock_oncopanel.assert_called_once()


@pytest.mark.anyio
async def test_oncopanel_extraction_persists_pending():
    """#398 Phase 3b — extraction result stored under pending_oncopanel:*
    for physician review; NOT auto-merged into PatientProfile."""
    from oncoteam.autonomous_tasks import run_oncopanel_extraction_single

    mock_result = {
        "response": '```json\n{"panel_id": "q1b_test", "variants": []}\n```',
        "cost": 0.012,
        "tool_calls": [],
        "error": None,
        "model": "sonnet",
    }

    captured_state: dict[str, dict] = {}

    async def fake_set_state(key, value, *, token=None):
        captured_state[key] = value

    with (
        patch(
            "oncoteam.autonomous_tasks._run_single_doc_task",
            AsyncMock(return_value=mock_result),
        ),
        patch("oncoteam.autonomous_tasks._set_state", side_effect=fake_set_state),
    ):
        await run_oncopanel_extraction_single(700, patient_id="q1b")

    # Verify the pending proposal was persisted
    key = "pending_oncopanel:q1b:700"
    assert key in captured_state
    stored = captured_state[key]
    assert stored["status"] == "pending_physician_review"
    assert stored["document_id"] == 700
    assert stored["patient_id"] == "q1b"
    assert "raw_response" in stored
    assert "panel_id" in stored["raw_response"]
    assert stored["extraction_cost_usd"] == 0.012


@pytest.mark.anyio
async def test_oncopanel_extraction_skipped_for_general_health_patient():
    """e5g (Z00.0) is a general-health patient — no oncopanel context."""
    from oncoteam.autonomous_tasks import run_oncopanel_extraction_single

    result = await run_oncopanel_extraction_single(800, patient_id="e5g")
    assert result.get("skipped") is True
    assert result.get("reason") == "non_oncology_patient"


# ── Webhook endpoint ───────────────────────────


def _make_request(body: dict, headers: dict | None = None):
    """Create a mock Starlette Request with JSON body."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/internal/document-webhook",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
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
    """Valid webhook call should return pipeline_started (CEE night window)."""
    from oncoteam.dashboard_api import api_document_webhook

    # Sprint 99 / #438 bug 3 — patient_id is now required in webhook body.
    request = _make_request({"document_id": 42, "patient_id": "q1b", "category": "lab"})
    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        # Force always-in-CEE-night so this test is deterministic regardless of wall clock.
        patch("oncoteam.api_webhooks.DOC_WEBHOOK_CEE_NIGHT_HOURS", (0, 24)),
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
    assert data["dispatch"] == "immediate"


@pytest.mark.anyio
async def test_webhook_deduplication():
    """Webhook should return already_processed for duplicate document_id."""
    from oncoteam.dashboard_api import api_document_webhook

    # Sprint 99 / #438 bug 3 — patient_id is now required in webhook body.
    request = _make_request({"document_id": 42, "patient_id": "q1b"})
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


@pytest.mark.anyio
async def test_webhook_passes_patient_id():
    """Webhook should pass patient_id to pipeline for active (non-paused) patients."""
    from oncoteam.dashboard_api import api_document_webhook

    # q1b is the only active patient in Sprint 92. e5g/sgu are paused
    # (see test_webhook_paused_patient_skipped).
    request = _make_request({"document_id": 99, "patient_id": "q1b", "category": "lab"})
    mock_pipeline = AsyncMock(return_value={"ok": True})
    mock_get_state = AsyncMock(return_value={})

    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        patch("oncoteam.api_webhooks.DOC_WEBHOOK_CEE_NIGHT_HOURS", (0, 24)),
        patch("oncoteam.autonomous_tasks._get_state", mock_get_state),
        patch(
            "oncoteam.autonomous_tasks._extract_timestamp",
            return_value="",
        ),
        patch("oncoteam.autonomous_tasks.run_document_pipeline", mock_pipeline),
    ):
        resp = await api_document_webhook(request)

    data = json.loads(resp.body)
    assert data["status"] == "pipeline_started"
    assert data["patient_id"] == "q1b"

    # Verify pipeline was called with patient_id
    mock_pipeline.assert_called_once()
    call_kwargs = mock_pipeline.call_args
    assert call_kwargs[1]["patient_id"] == "q1b"


@pytest.mark.anyio
async def test_webhook_paused_patient_skipped():
    """Sprint 92 pause gate: paused patients get 202 skipped, no Claude spend."""
    from oncoteam.dashboard_api import api_document_webhook

    request = _make_request({"document_id": 200, "patient_id": "e5g", "category": "lab"})
    mock_pipeline = AsyncMock(return_value={"ok": True})

    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        patch("oncoteam.autonomous_tasks.run_document_pipeline", mock_pipeline),
    ):
        resp = await api_document_webhook(request)

    assert resp.status_code == 202
    data = json.loads(resp.body)
    assert data["status"] == "skipped_patient_paused"
    assert data["patient_id"] == "e5g"
    mock_pipeline.assert_not_called()


@pytest.mark.anyio
async def test_webhook_outside_cee_night_enqueues():
    """Uploads outside CEE night window are queued, not dispatched."""
    from oncoteam.dashboard_api import api_document_webhook

    request = _make_request({"document_id": 300, "patient_id": "q1b", "category": "lab"})
    mock_pipeline = AsyncMock(return_value={"ok": True})
    stored: dict = {}

    async def fake_set_state(key, value, *, token=None):
        stored[key] = value

    with (
        patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""),
        patch("oncoteam.dashboard_api.MCP_TRANSPORT", "stdio"),
        # Empty window → every real hour is "outside" → always enqueue.
        patch("oncoteam.api_webhooks.DOC_WEBHOOK_CEE_NIGHT_HOURS", (99, 99)),
        patch("oncoteam.autonomous_tasks._get_state", AsyncMock(return_value={})),
        patch("oncoteam.autonomous_tasks._extract_timestamp", return_value=""),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock(side_effect=fake_set_state)),
        patch("oncoteam.autonomous_tasks.run_document_pipeline", mock_pipeline),
    ):
        resp = await api_document_webhook(request)

    assert resp.status_code == 202
    data = json.loads(resp.body)
    assert data["status"] == "queued_for_cee_night"
    assert data["dispatch"] == "queued"
    assert data["queue_len"] == 1
    # Pipeline is NOT called — document sits in queue until drain.
    mock_pipeline.assert_not_called()
    # Queue state was persisted.
    assert "pending_docs_queue" in stored
    queued = stored["pending_docs_queue"]["docs"]
    assert len(queued) == 1
    assert queued[0]["doc_id"] == 300
