"""Tests for autonomous agent loop."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam.autonomous import (
    AUTONOMOUS_SYSTEM_PROMPT,
    TOOLS,
    _track_cost,
    execute_tool,
    get_daily_cost,
    run_autonomous_task,
)


class TestSystemPrompt:
    def test_contains_patient_profile(self):
        assert "KRAS G12S" in AUTONOMOUS_SYSTEM_PROMPT

    def test_contains_biomarker_rules(self):
        assert "anti-EGFR" in AUTONOMOUS_SYSTEM_PROMPT
        assert "CONTRAINDICATED" in AUTONOMOUS_SYSTEM_PROMPT

    def test_contains_clinical_protocol(self):
        assert "Lab Safety Thresholds" in AUTONOMOUS_SYSTEM_PROMPT
        assert "Dose Modification" in AUTONOMOUS_SYSTEM_PROMPT
        assert "Treatment Milestones" in AUTONOMOUS_SYSTEM_PROMPT

    def test_contains_safety_instructions(self):
        assert "physician review" in AUTONOMOUS_SYSTEM_PROMPT
        assert "NEEDS_PHYSICIAN_REVIEW" in AUTONOMOUS_SYSTEM_PROMPT


class TestTools:
    def test_tools_defined(self):
        assert len(TOOLS) >= 7
        tool_names = {t["name"] for t in TOOLS}
        assert "search_pubmed" in tool_names
        assert "search_trials" in tool_names
        assert "check_trial_eligibility" in tool_names
        assert "store_briefing" in tool_names

    def test_all_tools_have_schema(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_search_pubmed(self):
        with patch("oncoteam.autonomous.pubmed_client") as mock:
            article = MagicMock()
            article.model_dump.return_value = {"pmid": "123", "title": "Test"}
            mock.search_pubmed = AsyncMock(return_value=[article])

            result = await execute_tool("search_pubmed", {"query": "test", "max_results": 3})
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["pmid"] == "123"
            mock.search_pubmed.assert_called_once_with("test", 3)

    @pytest.mark.asyncio
    async def test_search_documents(self):
        with patch("oncoteam.autonomous.oncofiles_client") as mock:
            mock.search_documents = AsyncMock(return_value={"documents": [{"id": 1}]})

            result = await execute_tool("search_documents", {"text": "lab"})
            data = json.loads(result)
            assert len(data) == 1

    @pytest.mark.asyncio
    async def test_store_briefing(self):
        with patch("oncoteam.autonomous.log_to_diary") as mock:
            mock.return_value = None

            result = await execute_tool(
                "store_briefing",
                {"title": "Test", "content": "Content", "tags": ["test"]},
            )
            data = json.loads(result)
            assert data["stored"] is True
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = await execute_tool("nonexistent", {})
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        with patch("oncoteam.autonomous.pubmed_client") as mock:
            mock.search_pubmed = AsyncMock(side_effect=Exception("API down"))

            result = await execute_tool("search_pubmed", {"query": "test"})
            data = json.loads(result)
            assert "error" in data
            assert "API down" in data["error"]


class TestCostTracking:
    def test_track_cost(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = 0.0
        mod._daily_cost_reset_date = ""

        cost = _track_cost(1000, 500)
        assert cost > 0
        assert get_daily_cost() == cost

    def test_cost_accumulates(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = 0.0
        mod._daily_cost_reset_date = ""

        cost1 = _track_cost(1000, 500)
        cost2 = _track_cost(2000, 1000)
        assert get_daily_cost() == pytest.approx(cost1 + cost2)


class TestExtractTimestamp:
    """Tests for _extract_timestamp, fixing the NoneType.get crash."""

    def test_none_input(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp(None) == ""

    def test_empty_dict(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({}) == ""

    def test_flat_format(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({"timestamp": "2026-03-10"}) == "2026-03-10"

    def test_nested_dict(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({"value": {"timestamp": "2026-03-10"}}) == "2026-03-10"

    def test_nested_json_string(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({"value": '{"timestamp": "2026-03-10"}'}) == "2026-03-10"

    def test_value_none(self):
        """This is the exact case that caused the production crash."""
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({"value": None}) == ""

    def test_full_agent_state_row(self):
        from oncoteam.autonomous_tasks import _extract_timestamp

        assert _extract_timestamp({"key": "last_file_scan", "value": None, "agent_id": "oncoteam"}) == ""


class TestRunAutonomousTask:
    @pytest.mark.asyncio
    async def test_cost_limit_abort(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = 100.0  # Over limit
        mod._daily_cost_reset_date = ""

        result = await run_autonomous_task("test prompt")
        assert "error" in result
        assert "cost limit" in result["error"].lower()

        # Reset
        mod._daily_cost = 0.0

    @pytest.mark.asyncio
    async def test_basic_run_no_tools(self):
        """Test a simple run where Claude responds without using tools."""
        import oncoteam.autonomous as mod

        mod._daily_cost = 0.0
        mod._daily_cost_reset_date = ""

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.stop_reason = "end_turn"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Test response"
        mock_response.content = [text_block]

        with patch("oncoteam.autonomous._get_client") as mock_client:
            client = AsyncMock()
            client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            result = await run_autonomous_task("test prompt", task_name="test")

            assert result["response"] == "Test response"
            assert result["input_tokens"] == 100
            assert result["output_tokens"] == 200
            assert result["cost"] > 0
            assert result["task_name"] == "test"
            assert result["tool_calls"] == []

    @pytest.mark.asyncio
    async def test_run_with_thinking(self):
        """Test that thinking blocks are captured."""
        import oncoteam.autonomous as mod

        mod._daily_cost = 0.0
        mod._daily_cost_reset_date = ""

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.stop_reason = "end_turn"

        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Let me analyze this..."

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Here is my analysis."
        mock_response.content = [thinking_block, text_block]

        with patch("oncoteam.autonomous._get_client") as mock_client:
            client = AsyncMock()
            client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            result = await run_autonomous_task("analyze something")

            assert len(result["thinking"]) == 1
            assert "analyze this" in result["thinking"][0]
            assert result["response"] == "Here is my analysis."
