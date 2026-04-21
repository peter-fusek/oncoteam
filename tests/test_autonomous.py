"""Tests for autonomous agent loop."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam.autonomous import (
    TOOLS,
    _track_cost,
    build_system_prompt,
    execute_tool,
    get_daily_cost,
    run_autonomous_task,
)
from oncoteam.models import PatientProfile


class TestSystemPrompt:
    def test_contains_patient_profile(self):
        prompt = build_system_prompt("q1b")
        assert "KRAS G12S" in prompt

    def test_contains_biomarker_rules(self):
        prompt = build_system_prompt("q1b")
        assert "anti-EGFR" in prompt

    def test_contains_clinical_protocol(self):
        prompt = build_system_prompt("q1b")
        assert "Lab Safety Thresholds" in prompt
        assert "Dose Modification" in prompt
        assert "Treatment Milestones" in prompt

    def test_contains_safety_instructions(self):
        prompt = build_system_prompt("q1b")
        assert "physician review" in prompt
        assert "NEEDS_PHYSICIAN_REVIEW" in prompt


class TestGeneralHealthPrompt:
    """System prompt for general health (non-oncology) patients."""

    def test_e5g_gets_general_health_header(self):
        prompt = build_system_prompt("e5g")
        assert "general preventive care" in prompt
        assert "cancer treatment management" not in prompt

    def test_e5g_no_oncology_protocol(self):
        prompt = build_system_prompt("e5g")
        assert "mFOLFOX6" not in prompt
        assert "Dose Modification" not in prompt
        assert "Treatment Milestones" not in prompt
        assert "NCCN" not in prompt
        assert "SII" not in prompt

    def test_e5g_has_general_health_content(self):
        prompt = build_system_prompt("e5g")
        assert "EU/WHO" in prompt or "ESC" in prompt
        assert "Preventive care" in prompt
        assert "glucose" in prompt.lower()

    def test_e5g_has_patient_profile(self):
        prompt = build_system_prompt("e5g")
        assert "Peter F." in prompt
        assert "Z00.0" in prompt

    def test_e5g_ends_with_preventive_reminders_instruction(self):
        prompt = build_system_prompt("e5g")
        assert "Preventive care reminders" in prompt
        assert "Questions for Oncologist" not in prompt

    def test_erika_still_gets_oncology(self):
        """Regression: oncology patients must NOT be affected."""
        prompt = build_system_prompt("q1b")
        assert "cancer treatment" in prompt
        assert "Lab Safety Thresholds" in prompt
        assert "KRAS G12S" in prompt
        assert "general preventive care" not in prompt


class TestTools:
    def test_tools_defined(self):
        assert len(TOOLS) >= 11
        tool_names = {t["name"] for t in TOOLS}
        assert "search_pubmed" in tool_names
        assert "search_trials" in tool_names
        assert "check_trial_eligibility" in tool_names
        assert "store_briefing" in tool_names
        assert "view_document" in tool_names
        assert "store_lab_values" in tool_names
        assert "add_treatment_event" in tool_names

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
    async def test_view_document(self):
        with patch("oncoteam.autonomous.oncofiles_client") as mock:
            mock.view_document = AsyncMock(return_value={"content": "Lab results..."})

            result = await execute_tool("view_document", {"document_id": 42})
            data = json.loads(result)
            assert data["content"] == "Lab results..."
            mock.view_document.assert_called_once_with("42", token=None)

    @pytest.mark.asyncio
    async def test_store_lab_values(self):
        with patch("oncoteam.autonomous.oncofiles_client") as mock:
            mock.store_lab_values = AsyncMock(return_value={"stored": 3})

            result = await execute_tool(
                "store_lab_values",
                {"document_id": 1, "lab_date": "2026-03-10", "values": {"ANC": 3200}},
            )
            data = json.loads(result)
            assert data["stored"] == 3
            mock.store_lab_values.assert_called_once_with(
                document_id=1, lab_date="2026-03-10", values_json='{"ANC": 3200}', token=None
            )

    @pytest.mark.asyncio
    async def test_add_treatment_event(self):
        with patch("oncoteam.autonomous.oncofiles_client") as mock:
            mock.add_treatment_event = AsyncMock(return_value={"id": 99})

            result = await execute_tool(
                "add_treatment_event",
                {
                    "event_date": "2026-03-10",
                    "event_type": "lab_result",
                    "title": "Pre-cycle 3 CBC",
                    "metadata": {"ANC": 3200, "PLT": 180000},
                },
            )
            data = json.loads(result)
            assert data["id"] == 99
            mock.add_treatment_event.assert_called_once()

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

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""

        cost = _track_cost(1000, 500)
        assert cost > 0
        assert get_daily_cost() == cost

    def test_cost_accumulates(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""

        cost1 = _track_cost(1000, 500)
        cost2 = _track_cost(2000, 1000)
        assert get_daily_cost() == pytest.approx(cost1 + cost2)

    def test_track_cost_sonnet_rates(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""

        cost = _track_cost(1_000_000, 1_000_000, "claude-sonnet-4-6")
        # $3 input + $15 output = $18
        assert cost == pytest.approx(18.0)

    def test_track_cost_haiku_rates(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""

        cost = _track_cost(1_000_000, 1_000_000, "claude-haiku-4-5-20251001")
        # $0.80 input + $4.0 output = $4.80
        assert cost == pytest.approx(4.8)

    def test_haiku_cheaper_than_sonnet(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""
        haiku_cost = _track_cost(1000, 500, "claude-haiku-4-5-20251001")

        mod._daily_cost = {}
        sonnet_cost = _track_cost(1000, 500, "claude-sonnet-4-6")

        assert haiku_cost < sonnet_cost


class TestCooldownGuard:
    """Tests for _should_skip cooldown logic (#75)."""

    @pytest.mark.asyncio
    async def test_skip_when_recently_run(self):
        from oncoteam.autonomous_tasks import _should_skip

        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        recent_ts = now.isoformat()

        with patch("oncoteam.autonomous_tasks._get_state") as mock:
            mock.return_value = {"timestamp": recent_ts}
            assert await _should_skip("file_scan") is True

    @pytest.mark.asyncio
    async def test_no_skip_when_never_run(self):
        from oncoteam.autonomous_tasks import _should_skip

        with patch("oncoteam.autonomous_tasks._get_state") as mock:
            mock.return_value = {}
            assert await _should_skip("file_scan") is False

    @pytest.mark.asyncio
    async def test_no_skip_when_cooldown_expired(self):
        from oncoteam.autonomous_tasks import _should_skip

        old_ts = "2020-01-01T00:00:00+00:00"

        with patch("oncoteam.autonomous_tasks._get_state") as mock:
            mock.return_value = {"timestamp": old_ts}
            assert await _should_skip("file_scan") is False

    @pytest.mark.asyncio
    async def test_no_skip_for_unknown_task(self):
        from oncoteam.autonomous_tasks import _should_skip

        with patch("oncoteam.autonomous_tasks._get_state") as mock:
            mock.return_value = {}
            assert await _should_skip("unknown_task") is False

    @pytest.mark.asyncio
    async def test_task_returns_skipped_dict(self):
        from oncoteam.autonomous_tasks import run_file_scan

        with patch("oncoteam.autonomous_tasks._should_skip", return_value=True):
            result = await run_file_scan()
            assert result["skipped"] is True
            assert result["reason"] == "cooldown"


class TestDdrMonitor:
    """Tests for run_ddr_monitor (#392) — DDR-deficient guard + proposals lane."""

    @pytest.mark.asyncio
    async def test_skips_when_patient_not_ddr_deficient(self):
        """Non-DDR-deficient patient: agent is a no-op, returns skipped dict."""
        from oncoteam.autonomous_tasks import run_ddr_monitor

        with patch("oncoteam.eligibility.is_ddr_deficient", return_value=False):
            result = await run_ddr_monitor(patient_id="e5g")
            assert result["skipped"] == "not_ddr_deficient"
            assert result["patient_id"] == "e5g"

    @pytest.mark.asyncio
    async def test_runs_when_patient_ddr_deficient(self):
        """q1b has ATM biallelic loss — agent should fire the autonomous task."""
        from oncoteam.autonomous_tasks import run_ddr_monitor

        mock_result = {"cost": 0.05, "response": "proposed 2 trials", "tool_calls": []}
        with (
            patch("oncoteam.eligibility.is_ddr_deficient", return_value=True),
            patch("oncoteam.autonomous_tasks._should_skip", return_value=False),
            patch("oncoteam.autonomous_tasks._get_state", return_value={}),
            patch("oncoteam.autonomous_tasks._set_state"),
            patch("oncoteam.autonomous_tasks._log_task"),
            patch(
                "oncoteam.autonomous_tasks.run_autonomous_task",
                return_value=mock_result,
            ) as mock_run,
        ):
            result = await run_ddr_monitor(patient_id="q1b")
            assert result == mock_result
            # Verify the prompt includes DDR variants + seed watchlist
            prompt_arg = mock_run.call_args[0][0]
            assert "ATM" in prompt_arg
            assert "PARPi" in prompt_arg
            assert "proposals lane" in prompt_arg.lower()
            assert "NCT05379985" in prompt_arg  # pan-RAS seed
            # Uses Sonnet (reasoning), not Haiku
            assert mock_run.call_args.kwargs.get("model") is not None


class TestDdrMonitorRegistry:
    """Tests for ddr_monitor AgentConfig in registry."""

    def test_registered(self):
        from oncoteam.agent_registry import AGENT_REGISTRY

        assert "ddr_monitor" in AGENT_REGISTRY

    def test_schedule_stacked_with_trial_monitor(self):
        """ddr_monitor fires Sat 02:15 UTC — 15 min before trial_monitor (02:30)."""
        from oncoteam.agent_registry import AGENT_REGISTRY

        agent = AGENT_REGISTRY["ddr_monitor"]
        assert agent.schedule_params["day_of_week"] == "sat"
        assert agent.schedule_params["hour"] == 2
        assert agent.schedule_params["minute"] == 15

    def test_no_whatsapp_push(self):
        """Proposals-only per #395 — no direct WA notification."""
        from oncoteam.agent_registry import AGENT_REGISTRY

        assert AGENT_REGISTRY["ddr_monitor"].whatsapp_enabled is False


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

        state = {"key": "last_file_scan", "value": None, "agent_id": "oncoteam"}
        assert _extract_timestamp(state) == ""


class TestUnwrapAgentState:
    """Tests for _unwrap_agent_state, fixing budget zeros regression."""

    def test_none_input(self):
        from oncoteam.autonomous import _unwrap_agent_state

        assert _unwrap_agent_state(None) == {}

    def test_empty_dict(self):
        from oncoteam.autonomous import _unwrap_agent_state

        assert _unwrap_agent_state({}) == {}

    def test_flat_format(self):
        from oncoteam.autonomous import _unwrap_agent_state

        result = _unwrap_agent_state({"month": "2026-03", "cost_usd": 5.0})
        assert result["month"] == "2026-03"
        assert result["cost_usd"] == 5.0

    def test_nested_dict_format(self):
        from oncoteam.autonomous import _unwrap_agent_state

        result = _unwrap_agent_state({"value": {"month": "2026-03", "cost_usd": 5.0}})
        assert result["month"] == "2026-03"
        assert result["cost_usd"] == 5.0

    def test_nested_json_string_format(self):
        from oncoteam.autonomous import _unwrap_agent_state

        result = _unwrap_agent_state({"value": '{"date": "2026-03-11", "cost_usd": 1.5}'})
        assert result["date"] == "2026-03-11"
        assert result["cost_usd"] == 1.5

    def test_value_none(self):
        from oncoteam.autonomous import _unwrap_agent_state

        assert _unwrap_agent_state({"value": None}) == {}

    def test_value_invalid_json(self):
        from oncoteam.autonomous import _unwrap_agent_state

        assert _unwrap_agent_state({"value": "not json"}) == {}


class TestBiomarkerRulesCrossPatient:
    """Ensure build_system_prompt produces patient-specific biomarker rules."""

    def test_no_cross_contamination(self):
        from oncoteam.patient_context import (
            _patient_registry,
            _patient_research_terms,
            _patient_tokens,
            build_biomarker_rules,
            build_patient_profile_text,
            register_patient,
        )

        jan_profile = PatientProfile(
            patient_id="jan",
            name="Ján Testovič",
            diagnosis_code="C50.9",
            diagnosis_description="Breast cancer, HER2-positive",
            tumor_site="Breast",
            biomarkers={
                "KRAS": "Wild-type",
                "HER2": "Positive (3+)",
                "MSI": "MSI-H/dMMR",
            },
            treatment_regimen="Trastuzumab + Pertuzumab + Docetaxel",
            hospitals=["Test Hospital"],
            excluded_therapies={},
        )

        # Save original registry state for cleanup
        had_jan = "jan" in _patient_registry
        orig_token = _patient_tokens.get("jan")
        orig_terms = _patient_research_terms.get("jan")

        try:
            register_patient("jan", "tok_jan", jan_profile, research_terms=["breast cancer HER2"])

            # Check patient-specific sections (biomarker rules + profile text)
            jan_rules = build_biomarker_rules(jan_profile)
            jan_profile_text = build_patient_profile_text(jan_profile)
            jan_prompt = build_system_prompt("jan")

            # Jan's biomarker rules must NOT contain Erika's KRAS G12S
            assert "G12S" not in jan_rules
            assert "anti-EGFR" not in jan_rules.lower() or "excluded" not in jan_rules.lower()
            # Jan's profile must NOT mention Erika's mutation
            assert "G12S" not in jan_profile_text
            # Jan's prompt MUST reflect his own biomarkers
            assert "HER2" in jan_prompt
            assert "Ján Testovič" in jan_prompt

            # Erika's prompt MUST still have her KRAS G12S
            erika_prompt = build_system_prompt("q1b")
            assert "G12S" in erika_prompt
        finally:
            # Clean up registry
            if not had_jan:
                _patient_registry.pop("jan", None)
                _patient_tokens.pop("jan", None)
                _patient_research_terms.pop("jan", None)
            else:
                if orig_token is not None:
                    _patient_tokens["jan"] = orig_token
                if orig_terms is not None:
                    _patient_research_terms["jan"] = orig_terms


class TestRunAutonomousTask:
    @pytest.mark.asyncio
    async def test_cost_limit_abort(self):
        import oncoteam.autonomous as mod

        mod._daily_cost = {"global": 100.0}  # Over limit
        mod._daily_cost_reset_date = ""

        result = await run_autonomous_task("test prompt")
        assert "error" in result
        assert "cost limit" in result["error"].lower()

        # Reset
        mod._daily_cost = {}

    @pytest.mark.asyncio
    async def test_basic_run_no_tools(self):
        """Test a simple run where Claude responds without using tools."""
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
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
            assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_run_with_thinking(self):
        """Test that thinking blocks are captured."""
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
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

    @pytest.mark.asyncio
    async def test_run_with_citations(self):
        """Test that citations are extracted from text blocks."""
        import oncoteam.autonomous as mod

        mod._daily_cost = {}
        mod._daily_cost_reset_date = ""

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.stop_reason = "end_turn"

        citation = MagicMock()
        citation.cited_text = "FOLFOX is first-line for mCRC"
        citation.document_title = "search_pubmed result"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "According to research, FOLFOX is standard."
        text_block.citations = [citation]
        mock_response.content = [text_block]

        with patch("oncoteam.autonomous._get_client") as mock_client:
            client = AsyncMock()
            client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            result = await run_autonomous_task("test citations")

            assert len(result["citations"]) == 1
            assert "FOLFOX" in result["citations"][0]["cited_text"]
            assert result["citations"][0]["source"] == "search_pubmed result"


class TestNotificationPolicyGate:
    """#391 — _send_whatsapp suppresses push for patients with policy=silent.

    Default policy for newly-onboarded patients is "silent" so parity /
    read-only patients don't spam the admin inbox. Explicit opt-in via
    PatientProfile.notification_policy = "admin" is required.
    """

    @pytest.mark.anyio
    async def test_send_whatsapp_suppresses_silent_patient(self):
        from oncoteam.autonomous_tasks import _send_whatsapp

        with patch("httpx.AsyncClient") as mock_http:
            # sgu defaults to silent
            result = await _send_whatsapp("test msg", recipient="caregiver", patient_id="sgu")

        assert result.get("suppressed") == "policy:silent"
        mock_http.assert_not_called()

    @pytest.mark.anyio
    async def test_send_whatsapp_delivers_admin_patient(self):
        from oncoteam.autonomous_tasks import _send_whatsapp

        with patch("httpx.AsyncClient") as mock_http:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "sent": 1}
            mock_resp.raise_for_status = MagicMock()
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_http.return_value.__aenter__.return_value = client

            # q1b has policy="admin"
            result = await _send_whatsapp("test msg", recipient="caregiver", patient_id="q1b")

        assert "suppressed" not in result
        client.post.assert_called_once()

    @pytest.mark.anyio
    async def test_send_whatsapp_system_alert_bypasses_policy(self):
        """No patient_id → system-wide alert (health_monitor, daily_cost) —
        must always reach admin regardless of policy."""
        from oncoteam.autonomous_tasks import _send_whatsapp

        with patch("httpx.AsyncClient") as mock_http:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "sent": 1}
            mock_resp.raise_for_status = MagicMock()
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_http.return_value.__aenter__.return_value = client

            result = await _send_whatsapp("circuit breaker open", recipient="caregiver")

        assert "suppressed" not in result
        client.post.assert_called_once()
