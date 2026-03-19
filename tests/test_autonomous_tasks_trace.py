"""Tests for autonomous task run trace storage (#92)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.autonomous_tasks import _log_task


@pytest.mark.anyio
async def test_log_task_stores_trace():
    """_log_task should store run trace via log_conversation."""
    mock_activity = AsyncMock(return_value={})
    mock_conversation = AsyncMock(return_value={})

    result = {
        "model": "claude-sonnet-4-20250514",
        "thinking": ["step 1"],
        "tool_calls": [{"name": "search_pubmed"}],
        "response": "Found articles",
        "cost": 0.01,
        "duration_ms": 3000,
        "input_tokens": 500,
        "output_tokens": 200,
        "error": None,
    }

    with (
        patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", mock_activity),
        patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", mock_conversation),
    ):
        await _log_task("daily_research", result)

    # Verify activity log was called
    mock_activity.assert_called_once()

    # Verify trace was stored
    mock_conversation.assert_called_once()
    call_kwargs = mock_conversation.call_args
    assert call_kwargs.kwargs["title"].startswith("Agent run: daily_research")
    assert call_kwargs.kwargs["entry_type"] == "agent_run"
    assert "task:daily_research" in call_kwargs.kwargs["tags"]
    assert "sys:agent-run" in call_kwargs.kwargs["tags"]
    assert "cost:0.0100" in call_kwargs.kwargs["tags"]

    import json

    content = json.loads(call_kwargs.kwargs["content"])
    assert content["task_name"] == "daily_research"
    assert content["model"] == "claude-sonnet-4-20250514"
    assert content["cost"] == 0.01
    assert content["tool_calls"] == [{"name": "search_pubmed"}]


@pytest.mark.anyio
async def test_log_task_trace_error_suppressed():
    """Trace storage failure should not propagate."""
    mock_activity = AsyncMock(return_value={})
    mock_conversation = AsyncMock(side_effect=ConnectionError("timeout"))

    with (
        patch("oncoteam.autonomous_tasks.oncofiles_client.add_activity_log", mock_activity),
        patch("oncoteam.autonomous_tasks.oncofiles_client.log_conversation", mock_conversation),
        patch("oncoteam.autonomous_tasks.record_suppressed_error") as mock_error,
    ):
        await _log_task("file_scan", {"cost": 0})

    mock_error.assert_called()
    # Should have been called for trace storage failure
    assert any("store_trace" in str(c) for c in mock_error.call_args_list)
