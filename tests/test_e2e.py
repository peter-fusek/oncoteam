"""E2E persistence tests — run against real oncofiles.

Skip when ONCOFILES_MCP_URL not set.
Usage: ONCOFILES_MCP_URL=https://...oncofiles.../mcp uv run pytest tests/test_e2e.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ONCOFILES_MCP_URL"),
    reason="ONCOFILES_MCP_URL not set — skip E2E",
)


@pytest.fixture
def unique_id() -> str:
    return f"e2e-test-{uuid.uuid4().hex[:8]}"


class TestE2EPersistence:
    @pytest.mark.asyncio
    async def test_research_entry_roundtrip(self, unique_id: str):
        """add_research_entry → search_research finds it by title."""
        from oncoteam import oncofiles_client

        title = f"E2E test research {unique_id}"
        await oncofiles_client.add_research_entry(
            source="manual",
            external_id=unique_id,
            title=title,
            summary="Automated test entry",
            tags=["e2e-test"],
        )
        result = await oncofiles_client.search_research(text=title)
        # oncofiles returns flat list
        entries = result if isinstance(result, list) else result.get("entries", [])
        assert any(unique_id in str(e) for e in entries), f"Entry {unique_id} not found"

    @pytest.mark.asyncio
    async def test_treatment_event_roundtrip(self, unique_id: str):
        """add_treatment_event → list_treatment_events finds it."""
        from oncoteam import oncofiles_client

        await oncofiles_client.add_treatment_event(
            event_date="2026-03-05",
            event_type="consultation",
            title=f"E2E test event {unique_id}",
            notes="Automated test",
        )
        result = await oncofiles_client.list_treatment_events()
        # oncofiles returns flat list
        events = result if isinstance(result, list) else result.get("events", [])
        assert any(unique_id in str(e) for e in events), f"Event {unique_id} not found"

    @pytest.mark.asyncio
    async def test_activity_log_roundtrip(self, unique_id: str):
        """add_activity_log → search_activity_log finds it."""
        from oncoteam import oncofiles_client

        await oncofiles_client.add_activity_log(
            session_id=unique_id,
            agent_id="oncoteam-e2e",
            tool_name="e2e_test",
            input_summary="test input",
            output_summary="test output",
            duration_ms=42,
        )
        result = await oncofiles_client.search_activity_log(session_id=unique_id)
        # oncofiles returns flat list
        entries = result if isinstance(result, list) else result.get("entries", [])
        assert len(entries) >= 1, f"Activity log for session {unique_id} not found"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="oncofiles set_agent_state has server-side bug")
    async def test_agent_state_roundtrip(self, unique_id: str):
        """set_agent_state → get_agent_state returns it."""
        import json

        from oncoteam import oncofiles_client

        key = f"e2e_test_{unique_id}"
        value = {"test": True, "id": unique_id}
        await oncofiles_client.set_agent_state(key=key, value=value)
        result = await oncofiles_client.get_agent_state(key=key)
        assert isinstance(result, dict)
        state = result.get("value") or result.get("state", {})
        if isinstance(state, str):
            state = json.loads(state)
        assert state.get("test") is True
