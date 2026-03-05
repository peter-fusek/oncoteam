"""Tests for activity_logger.py.

Covers the @log_activity decorator, session ID generation,
input/output summarizers, and log_to_diary helper.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.activity_logger import (
    _summarize_input,
    _summarize_output,
    get_session_id,
    log_activity,
    log_to_diary,
)

# ── get_session_id ────────────────────────────────


class TestGetSessionId:
    def test_format(self):
        sid = get_session_id()
        assert re.match(r"^\d{8}-[0-9a-f]{8}$", sid)

    def test_stable_within_process(self):
        assert get_session_id() == get_session_id()


# ── @log_activity decorator ──────────────────────


class TestLogActivityDecorator:
    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    async def test_returns_original_value(self, mock_log):
        @log_activity
        async def my_tool(query: str) -> str:
            return "result"

        result = await my_tool(query="test")
        assert result == "result"

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    async def test_logs_success(self, mock_log):
        @log_activity
        async def my_tool(query: str) -> str:
            return "result"

        await my_tool(query="test")

        mock_log.assert_called_once()
        args = mock_log.call_args[0]
        assert args[0] == "my_tool"  # tool_name
        assert args[1] == {"query": "test"}  # inputs
        assert args[2] == "result"  # output
        assert isinstance(args[3], int)  # duration_ms
        assert args[4] == "ok"  # status

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    async def test_logs_error_and_reraises(self, mock_log):
        @log_activity
        async def failing_tool() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await failing_tool()

        mock_log.assert_called_once()
        args = mock_log.call_args[0]
        assert args[0] == "failing_tool"
        assert args[2] is None  # output
        assert args[4] == "error"
        assert args[5] == "boom"  # error message

    @pytest.mark.asyncio
    @patch(
        "oncoteam.activity_logger._write_tool_log",
        new_callable=AsyncMock,
        side_effect=Exception("logging failed"),
    )
    async def test_fire_and_forget_on_success(self, mock_log):
        @log_activity
        async def my_tool() -> str:
            return "ok"

        result = await my_tool()
        assert result == "ok"

    @pytest.mark.asyncio
    @patch(
        "oncoteam.activity_logger._write_tool_log",
        new_callable=AsyncMock,
        side_effect=Exception("logging failed"),
    )
    async def test_fire_and_forget_on_error(self, mock_log):
        @log_activity
        async def failing_tool() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await failing_tool()

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    async def test_binds_positional_args(self, mock_log):
        @log_activity
        async def my_tool(query: str, limit: int = 10) -> str:
            return "done"

        await my_tool("hello", 5)

        args = mock_log.call_args[0]
        assert args[1] == {"query": "hello", "limit": 5}

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger._write_tool_log", new_callable=AsyncMock)
    async def test_measures_duration(self, mock_log):
        @log_activity
        async def my_tool() -> str:
            return "ok"

        await my_tool()

        duration_ms = mock_log.call_args[0][3]
        assert duration_ms >= 0


# ── _summarize_input ─────────────────────────────


class TestSummarizeInput:
    def test_search_pubmed(self):
        result = _summarize_input("search_pubmed", {"query": "FOLFOX", "max_results": 10})
        assert "FOLFOX" in result
        assert "10" in result

    def test_search_clinical_trials(self):
        result = _summarize_input(
            "search_clinical_trials",
            {"condition": "colorectal cancer", "intervention": "FOLFOX", "max_results": 10},
        )
        assert "colorectal cancer" in result
        assert "FOLFOX" in result

    def test_daily_briefing(self):
        assert _summarize_input("daily_briefing", {}) == ""

    def test_get_lab_trends(self):
        result = _summarize_input("get_lab_trends", {"limit": 5})
        assert "5" in result

    def test_search_documents(self):
        result = _summarize_input("search_documents", {"text": "lab", "category": "labs"})
        assert "lab" in result

    def test_get_patient_context(self):
        assert _summarize_input("get_patient_context", {}) == ""

    def test_unknown_tool_fallback(self):
        result = _summarize_input("unknown_tool", {"a": 1, "b": "two"})
        assert "a=" in result
        assert "b=" in result

    def test_empty_inputs(self):
        assert _summarize_input("search_pubmed", {}) == ""


# ── _summarize_output ────────────────────────────


class TestSummarizeOutput:
    def test_search_pubmed(self):
        output = json.dumps({"query": "test", "count": 7, "articles": []})
        assert _summarize_output("search_pubmed", output) == "7 articles found"

    def test_search_clinical_trials(self):
        output = json.dumps({"count": 3, "trials": []})
        assert _summarize_output("search_clinical_trials", output) == "3 trials found"

    def test_daily_briefing(self):
        output = json.dumps({"pubmed_articles": 12, "clinical_trials": 3})
        assert _summarize_output("daily_briefing", output) == "12 articles, 3 trials"

    def test_get_lab_trends(self):
        output = json.dumps({"lab_documents": {"documents": [{"id": 1}, {"id": 2}]}})
        assert _summarize_output("get_lab_trends", output) == "2 lab documents"

    def test_search_documents(self):
        output = json.dumps({"results": {"documents": [{"id": 1}]}})
        assert _summarize_output("search_documents", output) == "1 documents found"

    def test_get_patient_context(self):
        output = json.dumps({"name": "Test"})
        assert _summarize_output("get_patient_context", output) == "patient profile returned"

    def test_none_output(self):
        assert _summarize_output("any_tool", None) == ""

    def test_non_json_output(self):
        result = _summarize_output("any_tool", "plain text result")
        assert result == "plain text result"


# ── log_to_diary ─────────────────────────────────


class TestLogToDiary:
    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger.oncofiles_client.log_conversation", new_callable=AsyncMock)
    async def test_calls_log_conversation(self, mock_log):
        mock_log.return_value = {"id": 1}

        await log_to_diary(
            "Test title", "Test content", entry_type="decision", tags=["tag1", "tag2"]
        )

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["title"] == "Test title"
        assert kwargs["content"] == "Test content"
        assert kwargs["entry_type"] == "decision"
        assert kwargs["participant"] == "oncoteam"
        assert kwargs["tags"] == "tag1,tag2"

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger.oncofiles_client.log_conversation", new_callable=AsyncMock)
    async def test_defaults(self, mock_log):
        mock_log.return_value = {"id": 1}

        await log_to_diary("Title", "Content")

        kwargs = mock_log.call_args.kwargs
        assert kwargs["entry_type"] == "note"
        assert kwargs["tags"] is None
