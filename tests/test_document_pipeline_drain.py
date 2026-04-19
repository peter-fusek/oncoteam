"""Tests for run_document_pipeline_drain — nightly CEE-night doc processing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.anyio
async def test_drain_empty_queue():
    """Empty queue → drained=0, no pipeline calls."""
    from oncoteam.autonomous_tasks import run_document_pipeline_drain

    with (
        patch(
            "oncoteam.autonomous_tasks._get_state",
            AsyncMock(return_value={"docs": []}),
        ),
        patch(
            "oncoteam.autonomous_tasks._set_state",
            AsyncMock(return_value=None),
        ),
        patch(
            "oncoteam.autonomous_tasks.run_document_pipeline",
            AsyncMock(return_value={"ok": True, "cost": 0}),
        ) as mock_pipe,
        patch(
            "oncoteam.autonomous_tasks._log_task",
            AsyncMock(return_value=None),
        ),
    ):
        result = await run_document_pipeline_drain(patient_id="q1b")

    assert result["drained"] == 0
    assert result["patient_id"] == "q1b"
    mock_pipe.assert_not_called()


@pytest.mark.anyio
async def test_drain_processes_queued_docs():
    """Two queued docs → two pipeline calls, queue reset, cost aggregated."""
    from oncoteam.autonomous_tasks import run_document_pipeline_drain

    stored: dict = {}

    async def fake_set(key, value, *, token=None):
        stored[key] = value

    with (
        patch(
            "oncoteam.autonomous_tasks._get_state",
            AsyncMock(
                return_value={
                    "docs": [
                        {"doc_id": 101, "metadata": {"category": "lab"}},
                        {"doc_id": 102, "metadata": {"category": "report"}},
                    ]
                }
            ),
        ),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock(side_effect=fake_set)),
        patch(
            "oncoteam.autonomous_tasks.run_document_pipeline",
            AsyncMock(return_value={"ok": True, "cost": 0.003}),
        ) as mock_pipe,
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock(return_value=None)),
    ):
        result = await run_document_pipeline_drain(patient_id="q1b")

    assert result["drained"] == 2
    assert result["cost"] == pytest.approx(0.006)
    assert mock_pipe.await_count == 2
    # Queue was reset before processing to prevent re-runs on next night.
    assert stored.get("pending_docs_queue") == {"docs": []}


@pytest.mark.anyio
async def test_drain_skips_paused_patient():
    """Paused patient → zero work, no oncofiles reads."""
    from oncoteam.autonomous_tasks import run_document_pipeline_drain

    mock_get_state = AsyncMock(return_value={"docs": [{"doc_id": 1}]})
    mock_pipe = AsyncMock()

    with (
        patch("oncoteam.autonomous_tasks._get_state", mock_get_state),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock(return_value=None)),
        patch("oncoteam.autonomous_tasks.run_document_pipeline", mock_pipe),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock(return_value=None)),
    ):
        result = await run_document_pipeline_drain(patient_id="e5g")

    assert result["drained"] == 0
    assert result.get("skipped") == "patient_paused"
    mock_get_state.assert_not_called()
    mock_pipe.assert_not_called()


@pytest.mark.anyio
async def test_drain_handles_pipeline_error():
    """If one doc errors, drain continues for the rest."""
    from oncoteam.autonomous_tasks import run_document_pipeline_drain

    async def flaky_pipeline(doc_id, metadata=None, *, patient_id="q1b"):
        if doc_id == 201:
            raise RuntimeError("simulated failure")
        return {"ok": True, "cost": 0.002}

    with (
        patch(
            "oncoteam.autonomous_tasks._get_state",
            AsyncMock(
                return_value={
                    "docs": [
                        {"doc_id": 201},
                        {"doc_id": 202},
                    ]
                }
            ),
        ),
        patch("oncoteam.autonomous_tasks._set_state", AsyncMock(return_value=None)),
        patch(
            "oncoteam.autonomous_tasks.run_document_pipeline",
            AsyncMock(side_effect=flaky_pipeline),
        ),
        patch("oncoteam.autonomous_tasks._log_task", AsyncMock(return_value=None)),
    ):
        result = await run_document_pipeline_drain(patient_id="q1b")

    # Drain completed both docs (one ok, one error) — total cost = 0.002 from the ok one.
    assert result["drained"] == 2
    assert result["cost"] == pytest.approx(0.002)
