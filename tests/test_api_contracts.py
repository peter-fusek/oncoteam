"""API contract tests: validate response schemas for all dashboard endpoints.

These tests ensure API responses have the correct structure, preventing
blank-page regressions when keys are missing or silently swallowed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import (
    api_activity,
    api_autonomous,
    api_briefings,
    api_cumulative_dose,
    api_diagnostics,
    api_documents,
    api_family_update,
    api_labs,
    api_medications,
    api_patient,
    api_protocol,
    api_research,
    api_sessions,
    api_stats,
    api_status,
    api_timeline,
    api_toxicity,
    api_weight,
)

# ── Helpers ───────────────────────────────────────


def _make_request(query_string: str = "patient_id=q1b") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})
            self.method = "GET"

        async def json(self):
            return {}

    return FakeRequest(query_string)


def _parse(response) -> dict:
    return json.loads(response.body)


# ── Status ────────────────────────────────────────


@pytest.mark.anyio
async def test_status_contract():
    data = _parse(await api_status(_make_request()))
    assert data["status"] == "ok"
    assert "version" in data
    assert "tools_count" in data
    assert isinstance(data["tools"], list)


# ── List-based endpoints ──────────────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_activity_has_entries_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_activity(_make_request()))
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert "total" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_stats_has_stats_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_stats(_make_request()))
    assert "stats" in data
    assert isinstance(data["stats"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_timeline_has_events_key(mock):
    mock.return_value = {"events": []}
    data = _parse(await api_timeline(_make_request()))
    assert "events" in data
    assert isinstance(data["events"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_patient_context", new_callable=AsyncMock)
async def test_patient_has_required_keys(mock):
    mock.return_value = {"patient_ids": {}}
    data = _parse(await api_patient(_make_request()))
    assert "name" in data
    assert "therapy_categories" in data


@pytest.mark.anyio
@patch("oncoteam.api_research.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_research_has_entries_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_research(_make_request()))
    assert "entries" in data
    assert isinstance(data["entries"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_sessions_has_sessions_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_sessions(_make_request()))
    assert "sessions" in data
    assert isinstance(data["sessions"], list)
    assert "type_counts" in data
    assert "clinical" in data["type_counts"]
    assert "technical" in data["type_counts"]


@pytest.mark.anyio
@patch("oncoteam.api_agents.oncofiles_client.get_agent_state", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_activity_log", new_callable=AsyncMock)
@patch("oncoteam.api_agents.AUTONOMOUS_ENABLED", True)
async def test_autonomous_has_tasks_key(mock_log, mock_state):
    mock_log.return_value = {"entries": []}
    mock_state.return_value = {}
    data = _parse(await api_autonomous(_make_request()))
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_protocol_has_required_keys(mock_events, mock_trends):
    mock_events.return_value = {"events": []}
    mock_trends.return_value = {"trends": []}
    data = _parse(await api_protocol(_make_request()))
    assert "lab_thresholds" in data
    assert "monitoring_schedule" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_briefings_has_briefings_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_briefings(_make_request()))
    assert "briefings" in data
    assert isinstance(data["briefings"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_toxicity_has_entries_key(mock):
    mock.return_value = {"events": []}
    data = _parse(await api_toxicity(_make_request()))
    assert "entries" in data
    assert isinstance(data["entries"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.analyze_labs", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api.oncofiles_client.get_lab_trends_data", new_callable=AsyncMock)
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_labs_has_entries_and_reference(mock_events, mock_trends, mock_analyze):
    mock_events.return_value = {"events": []}
    mock_trends.return_value = {"trends": []}
    mock_analyze.return_value = {"entries": []}
    data = _parse(await api_labs(_make_request()))
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert "reference_ranges" in data


@pytest.mark.anyio
@patch("oncoteam.api_agents.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.list_research_entries", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_conversations", new_callable=AsyncMock)
@patch("oncoteam.api_agents.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_diagnostics_has_checks_key(mock_log, mock_conv, mock_research, mock_events):
    mock_events.return_value = {"events": []}
    mock_research.return_value = {"entries": []}
    mock_conv.return_value = {"entries": []}
    mock_log.return_value = {"entries": []}
    data = _parse(await api_diagnostics(_make_request()))
    assert "checks" in data
    assert isinstance(data["checks"], list)
    assert "healthy" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_medications_has_medications_key(mock):
    mock.return_value = {"events": []}
    data = _parse(await api_medications(_make_request()))
    assert "medications" in data
    assert isinstance(data["medications"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_weight_has_entries_key(mock):
    mock.return_value = {"events": []}
    data = _parse(await api_weight(_make_request()))
    assert "entries" in data
    assert isinstance(data["entries"], list)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_cumulative_dose_has_required_keys(mock_events):
    mock_events.return_value = {"events": []}
    data = _parse(await api_cumulative_dose(_make_request()))
    assert "drug" in data
    assert "cumulative_mg_m2" in data
    assert "all_thresholds" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_family_update_has_updates_key(mock):
    mock.return_value = {"entries": []}
    data = _parse(await api_family_update(_make_request()))
    assert "updates" in data
    assert isinstance(data["updates"], list)


# ── Data flow: data from oncofiles reaches response ──


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_activity_data_flows_through(mock):
    mock.return_value = {
        "entries": [
            {
                "tool_name": "search_pubmed",
                "status": "ok",
                "duration_ms": 100,
                "created_at": "2026-03-01T10:00:00Z",
                "input_summary": "q",
                "output_summary": "r",
                "error_message": None,
            }
        ]
    }
    data = _parse(await api_activity(_make_request()))
    assert data["total"] == 1
    assert data["entries"][0]["tool"] == "search_pubmed"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_briefings_data_flows_through(mock):
    mock.return_value = {
        "entries": [
            {
                "title": "Daily Briefing 2026-03-01",
                "content": "Research summary",
                "entry_type": "session_summary",
                "created_at": "2026-03-01T07:00:00Z",
                "tags": ["daily_briefing"],
            }
        ]
    }
    data = _parse(await api_briefings(_make_request()))
    assert data["total"] >= 1
    assert len(data["briefings"]) >= 1


# ── Circuit breaker fast-fail (#131) ─────────────


@pytest.mark.anyio
async def test_labs_circuit_breaker_open(
    _mock_circuit_breaker_closed,  # noqa: ARG001 — override the autouse fixture
):
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
        return_value={"state": "open", "failure_count": 5, "cooldown_remaining": 25},
    ):
        resp = await api_labs(_make_request())
        data = _parse(resp)
        assert resp.status_code == 503
        assert data["unavailable"] is True
        assert data["entries"] == []


@pytest.mark.anyio
async def test_documents_circuit_breaker_open(
    _mock_circuit_breaker_closed,  # noqa: ARG001 — override the autouse fixture
):
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
        return_value={"state": "open", "failure_count": 5, "cooldown_remaining": 25},
    ):
        resp = await api_documents(_make_request())
        data = _parse(resp)
        assert resp.status_code == 503
        assert data["unavailable"] is True
        assert data["documents"] == []
