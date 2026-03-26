"""Tests for /api/agents and /api/agents/{id}/runs endpoints (#92)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_agent_runs, api_agent_runs_all, api_agents


def _make_request(query_string: str = "", path_params: dict | None = None) -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str, params: dict | None):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})
            self.path_params = params or {}

    return FakeRequest(query_string, path_params)


@pytest.mark.anyio
async def test_agents_returns_non_system_agents():
    """Should return all agents except SYSTEM category."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        return_value={},
    ):
        request = _make_request()
        response = await api_agents(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    assert "agents" in data
    assert "total" in data
    # System agents (keepalive_ping, daily_cost_report) should be excluded
    agent_ids = [a["id"] for a in data["agents"]]
    assert "keepalive_ping" not in agent_ids
    assert "daily_cost_report" not in agent_ids
    # Should include non-system agents
    assert "daily_research" in agent_ids
    assert "pre_cycle_check" in agent_ids
    assert data["total"] == len(data["agents"])


@pytest.mark.anyio
async def test_agents_includes_expected_fields():
    """Each agent should have all required fields."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        return_value={},
    ):
        request = _make_request()
        response = await api_agents(request)
        data = json.loads(response.body)

    expected_fields = {
        "id",
        "name",
        "description",
        "category",
        "model",
        "schedule",
        "cooldown_hours",
        "max_turns",
        "whatsapp_enabled",
        "last_run",
        "enabled",
    }
    for agent in data["agents"]:
        assert expected_fields.issubset(agent.keys()), (
            f"Agent {agent['id']} missing fields: {expected_fields - agent.keys()}"
        )


@pytest.mark.anyio
async def test_agents_last_run_from_state():
    """Should populate last_run from agent state timestamp."""
    ts = "2026-03-17T10:00:00+00:00"
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        return_value={"timestamp": ts},
    ):
        request = _make_request()
        response = await api_agents(request)
        data = json.loads(response.body)

    dr = next(a for a in data["agents"] if a["id"] == "daily_research")
    assert dr["last_run"] == ts


@pytest.mark.anyio
async def test_agents_lang_en():
    """Should return English descriptions when ?lang=en."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_agent_state",
        new_callable=AsyncMock,
        return_value={},
    ):
        request = _make_request("lang=en")
        response = await api_agents(request)
        data = json.loads(response.body)

    dr = next(a for a in data["agents"] if a["id"] == "daily_research")
    assert dr["name"] == "PubMed research scan"


@pytest.mark.anyio
async def test_agent_runs_returns_traces():
    """Should return parsed run traces for a specific agent."""
    trace_content = json.dumps(
        {
            "task_name": "daily_research",
            "model": "claude-sonnet-4-20250514",
            "thinking": ["step1"],
            "tool_calls": [
                {"tool": "search_pubmed", "input": {"query": "CRC"}, "output": "3 results"},
            ],
            "response": "Found 3 articles",
            "prompt": "Search for CRC research",
            "cost": 0.012,
            "duration_ms": 5000,
            "input_tokens": 1000,
            "output_tokens": 500,
            "turns": 1,
            "started_at": "2026-03-18T10:00:00+00:00",
            "completed_at": "2026-03-18T10:00:05+00:00",
            "messages": [{"role": "user", "content": "Search for CRC research"}],
            "error": None,
        }
    )
    mock_result = {
        "entries": [
            {
                "id": 42,
                "created_at": "2026-03-17T10:00:00+00:00",
                "content": trace_content,
            }
        ]
    }
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        request = _make_request("limit=5", path_params={"id": "daily_research"})
        response = await api_agent_runs(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    assert data["agent_id"] == "daily_research"
    assert len(data["runs"]) == 1

    run = data["runs"][0]
    assert run["id"] == 42
    assert run["task_name"] == "daily_research"
    assert run["model"] == "claude-sonnet-4-20250514"
    assert run["cost"] == 0.012
    assert run["duration_ms"] == 5000
    assert run["input_tokens"] == 1000
    assert run["output_tokens"] == 500
    assert run["tool_call_count"] == 1
    assert run["turns"] == 1
    assert run["error"] is None


@pytest.mark.anyio
async def test_agent_runs_handles_invalid_content():
    """Should handle entries with non-JSON content gracefully."""
    mock_result = {
        "entries": [
            {
                "id": 99,
                "created_at": "2026-03-17T12:00:00+00:00",
                "content": "not json",
            }
        ]
    }
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        request = _make_request("", path_params={"id": "file_scan"})
        response = await api_agent_runs(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["task_name"] == "file_scan"  # falls back to agent_id
    assert run["cost"] == 0


@pytest.mark.anyio
async def test_agent_runs_error_returns_502():
    """Should return 502 when oncofiles is unreachable."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        side_effect=ConnectionError("timeout"),
    ):
        request = _make_request("", path_params={"id": "trial_monitor"})
        response = await api_agent_runs(request)
        data = json.loads(response.body)

    assert response.status_code == 502
    assert "error" in data
    assert data["runs"] == []


@pytest.mark.anyio
async def test_agent_runs_list_view_lightweight():
    """List view should return lightweight summary fields (no full response/prompt/messages)."""
    trace_content = json.dumps(
        {
            "response": "x" * 1000,
            "task_name": "test",
            "prompt": "test prompt",
            "tool_calls": [{"tool": "a"}],
        }
    )
    mock_result = {
        "entries": [{"id": 1, "created_at": "2026-03-17T10:00:00+00:00", "content": trace_content}]
    }
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        request = _make_request("", path_params={"id": "test"})
        response = await api_agent_runs(request)
        data = json.loads(response.body)

    run = data["runs"][0]
    assert run["task_name"] == "test"
    assert run["tool_call_count"] == 1
    # Full content fields should NOT be in list view
    assert "response" not in run
    assert "prompt" not in run
    assert "messages" not in run
    assert "tool_calls" not in run


# ── /api/agent-runs (aggregated) ────────────────────


@pytest.mark.anyio
async def test_agent_runs_all_returns_traces():
    """Aggregated endpoint returns runs across all agents with single MCP call."""
    trace1 = json.dumps({"task_name": "daily_research", "cost": 0.01, "tool_calls": []})
    trace2 = json.dumps({"task_name": "trial_monitor", "cost": 0.02, "tool_calls": [{"tool": "x"}]})
    mock_result = {
        "entries": [
            {
                "id": 1,
                "created_at": "2026-03-20T10:00:00+00:00",
                "tags": ["sys:agent-run", "task:daily_research"],
                "content": trace1,
            },
            {
                "id": 2,
                "created_at": "2026-03-20T09:00:00+00:00",
                "tags": ["sys:agent-run", "task:trial_monitor"],
                "content": trace2,
            },
        ]
    }
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_search:
        request = _make_request("limit=50")
        response = await api_agent_runs_all(request)
        data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["runs"]) == 2
    assert data["total"] == 2
    assert data["runs"][0]["task_name"] == "daily_research"
    assert data["runs"][1]["task_name"] == "trial_monitor"
    assert data["runs"][1]["tool_call_count"] == 1
    # Should use sys:agent-run tag only (no agent-specific filter)
    mock_search.assert_called_once_with(tags="sys:agent-run", limit=50, token=None)


@pytest.mark.anyio
async def test_agent_runs_all_error_returns_502():
    """Aggregated endpoint returns 502 when oncofiles is unreachable."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.search_conversations",
        new_callable=AsyncMock,
        side_effect=ConnectionError("timeout"),
    ):
        request = _make_request()
        response = await api_agent_runs_all(request)
        data = json.loads(response.body)

    assert response.status_code == 502
    assert data["runs"] == []
    assert "error" in data
