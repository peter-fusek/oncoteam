"""Tests for review_session tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.activity_logger import _suppressed_errors, get_session_id, record_suppressed_error


class TestReviewSession:
    @pytest.fixture(autouse=True)
    def _clear_suppressed(self):
        _suppressed_errors.clear()
        yield
        _suppressed_errors.clear()

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_conversations", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_activity_log", new_callable=AsyncMock)
    async def test_basic_review(self, mock_activity, mock_convos, mock_log):
        mock_activity.return_value = {
            "entries": [
                {
                    "tool_name": "search_pubmed",
                    "status": "ok",
                    "duration_ms": 150,
                    "input_summary": "query='FOLFOX'",
                    "output_summary": "5 articles found",
                    "error_message": None,
                    "created_at": "2026-03-06T10:00:00",
                },
                {
                    "tool_name": "search_clinical_trials",
                    "status": "error",
                    "duration_ms": 3000,
                    "input_summary": "condition='CRC'",
                    "output_summary": "",
                    "error_message": "timeout",
                    "created_at": "2026-03-06T10:01:00",
                },
            ],
        }
        mock_convos.return_value = {
            "entries": [
                {
                    "entry_type": "session_summary",
                    "content": "Reviewed FOLFOX trials",
                }
            ]
        }

        from oncoteam.server import review_session

        result = json.loads(await review_session.__wrapped__(session_id=get_session_id()))

        assert result["stats"]["total_calls"] == 2
        assert result["stats"]["errors"] == 1
        assert len(result["timeline"]) == 2
        assert result["errors"][0]["error"] == "timeout"
        assert result["session_summary"] == "Reviewed FOLFOX trials"

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_conversations", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_activity_log", new_callable=AsyncMock)
    async def test_includes_suppressed_errors(self, mock_activity, mock_convos, mock_log):
        mock_activity.return_value = {"entries": []}
        mock_convos.return_value = {"entries": []}

        record_suppressed_error("search_pubmed", "store_research", ValueError("connection lost"))

        from oncoteam.server import review_session

        result = json.loads(await review_session.__wrapped__())

        assert result["stats"]["suppressed_errors"] == 1
        assert result["suppressed_errors"][0]["tool"] == "search_pubmed"
        assert result["suppressed_errors"][0]["error"] == "connection lost"

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_conversations", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_activity_log", new_callable=AsyncMock)
    async def test_handles_oncofiles_failure(self, mock_activity, mock_convos, mock_log):
        mock_activity.side_effect = Exception("oncofiles down")
        mock_convos.side_effect = Exception("oncofiles down")

        from oncoteam.server import review_session

        result = json.loads(await review_session.__wrapped__())

        assert result["stats"]["total_calls"] == 0
        # The oncofiles errors should be recorded as suppressed
        assert result["stats"]["suppressed_errors"] >= 2

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_conversations", new_callable=AsyncMock)
    @patch("oncoteam.server.oncofiles_client.search_activity_log", new_callable=AsyncMock)
    async def test_empty_session(self, mock_activity, mock_convos, mock_log):
        mock_activity.return_value = {"entries": []}
        mock_convos.return_value = {"entries": []}

        from oncoteam.server import review_session

        result = json.loads(await review_session.__wrapped__())

        assert result["stats"]["total_calls"] == 0
        assert result["stats"]["errors"] == 0
        assert result["stats"]["avg_duration_ms"] == 0
        assert result["session_summary"] is None
