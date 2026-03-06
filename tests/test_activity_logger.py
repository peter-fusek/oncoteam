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
    _suppressed_errors,
    get_session_id,
    get_suppressed_errors,
    log_activity,
    log_to_diary,
    record_suppressed_error,
)

# ── Suppressed error buffer ──────────────────────


class TestSuppressedErrors:
    @pytest.fixture(autouse=True)
    def _clear(self):
        _suppressed_errors.clear()
        yield
        _suppressed_errors.clear()

    def test_record_and_get(self):
        record_suppressed_error("search_pubmed", "store_research", ValueError("conn lost"))
        errors = get_suppressed_errors()
        assert len(errors) == 1
        assert errors[0]["tool"] == "search_pubmed"
        assert errors[0]["phase"] == "store_research"
        assert errors[0]["error"] == "conn lost"
        assert errors[0]["type"] == "ValueError"
        assert "timestamp" in errors[0]

    def test_get_clears_buffer(self):
        record_suppressed_error("t", "p", RuntimeError("x"))
        assert len(get_suppressed_errors()) == 1
        assert len(get_suppressed_errors()) == 0

    def test_multiple_errors(self):
        record_suppressed_error("a", "p1", ValueError("e1"))
        record_suppressed_error("b", "p2", TypeError("e2"))
        errors = get_suppressed_errors()
        assert len(errors) == 2
        assert errors[0]["tool"] == "a"
        assert errors[1]["tool"] == "b"


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
        _suppressed_errors.clear()

        @log_activity
        async def my_tool() -> str:
            return "ok"

        result = await my_tool()
        assert result == "ok"
        # Logging failure should be captured in suppressed errors
        errors = get_suppressed_errors()
        assert len(errors) == 1
        assert errors[0]["phase"] == "activity_log"

    @pytest.mark.asyncio
    @patch(
        "oncoteam.activity_logger._write_tool_log",
        new_callable=AsyncMock,
        side_effect=Exception("logging failed"),
    )
    async def test_fire_and_forget_on_error(self, mock_log):
        _suppressed_errors.clear()

        @log_activity
        async def failing_tool() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await failing_tool()

        # Logging failure should be captured in suppressed errors
        errors = get_suppressed_errors()
        assert len(errors) == 1
        assert errors[0]["phase"] == "activity_log"

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

    def test_view_document(self):
        result = _summarize_input("view_document", {"file_id": "abc123"})
        assert "abc123" in result

    def test_analyze_labs(self):
        result = _summarize_input("analyze_labs", {"file_id": "abc123", "limit": 5})
        assert "abc123" in result
        assert "5" in result

    def test_compare_labs(self):
        result = _summarize_input("compare_labs", {"file_id_a": "a1", "file_id_b": "b2"})
        assert "a1" in result
        assert "b2" in result

    def test_fetch_pubmed_article(self):
        result = _summarize_input("fetch_pubmed_article", {"pmid": "12345678"})
        assert "12345678" in result

    def test_fetch_trial_details(self):
        result = _summarize_input("fetch_trial_details", {"nct_id": "NCT00001234"})
        assert "NCT00001234" in result

    def test_check_trial_eligibility(self):
        result = _summarize_input("check_trial_eligibility", {"nct_id": "NCT99999"})
        assert "NCT99999" in result

    def test_review_session(self):
        result = _summarize_input("review_session", {"session_id": "20260306-abc"})
        assert "20260306-abc" in result

    def test_create_improvement_issue(self):
        result = _summarize_input(
            "create_improvement_issue",
            {"repo": "instarea-sk/oncoteam", "title": "Fix something"},
        )
        assert "instarea-sk/oncoteam" in result

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

    def test_view_document(self):
        output = json.dumps({"text": "content"})
        assert _summarize_output("view_document", output) == "document content returned"

    def test_analyze_labs(self):
        output = json.dumps({"summary": "normal"})
        assert _summarize_output("analyze_labs", output) == "lab analysis returned"

    def test_compare_labs(self):
        output = json.dumps({"diff": []})
        assert _summarize_output("compare_labs", output) == "lab comparison returned"

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
        # Now includes session ID tag
        assert "tag1" in kwargs["tags"]
        assert "tag2" in kwargs["tags"]
        assert kwargs["tags"].startswith("sid:")

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger.oncofiles_client.log_conversation", new_callable=AsyncMock)
    async def test_defaults(self, mock_log):
        mock_log.return_value = {"id": 1}

        await log_to_diary("Title", "Content")

        kwargs = mock_log.call_args.kwargs
        assert kwargs["entry_type"] == "note"
        # Even with no user tags, session ID tag should be present
        assert kwargs["tags"].startswith("sid:")

    @pytest.mark.asyncio
    @patch("oncoteam.activity_logger.oncofiles_client.log_conversation", new_callable=AsyncMock)
    async def test_session_id_in_tags(self, mock_log):
        mock_log.return_value = {"id": 1}

        await log_to_diary("Title", "Content")

        kwargs = mock_log.call_args.kwargs
        sid = get_session_id()
        assert f"sid:{sid}" in kwargs["tags"]
