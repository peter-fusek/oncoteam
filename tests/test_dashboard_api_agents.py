"""Tests for /api/agents and /api/agents/{id}/runs endpoints (#92)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_agent_runs, api_agents


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
    assert run["tool_calls"][0]["tool"] == "search_pubmed"
    assert run["tool_calls"][0]["output"] == "3 results"
    assert run["tool_calls"][0]["has_full_output"] is False
    assert run["prompt"] == "Search for CRC research"
    assert run["turns"] == 1
    assert run["messages"] == [{"role": "user", "content": "Search for CRC research"}]
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
async def test_agent_runs_returns_full_response():
    """Should return full response without truncation (prompt observability)."""
    long_response = "x" * 1000
    trace_content = json.dumps(
        {"response": long_response, "task_name": "test", "prompt": "test prompt"}
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

    assert len(data["runs"][0]["response"]) == 1000
    assert data["runs"][0]["prompt"] == "test prompt"
