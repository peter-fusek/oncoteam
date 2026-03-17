"""Tests for /api/autonomous endpoint."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from oncoteam.dashboard_api import api_autonomous


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_returns_jobs():
    """Should return 14 jobs with assigned_tool field."""
    request = _make_request()
    response = await api_autonomous(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["enabled"] is True
    assert "daily_cost" in data
    assert len(data["jobs"]) == 14
    assert data["job_count"] == 14


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_jobs_have_assigned_tool():
    """Every job must have an assigned_tool for the task assignment UI."""
    request = _make_request()
    response = await api_autonomous(request)
    data = json.loads(response.body)

    for job in data["jobs"]:
        assert "assigned_tool" in job, f"Job {job['id']} missing assigned_tool"
        assert "id" in job
        assert "schedule" in job
        assert "description" in job


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_lang_en():
    """Should return English descriptions when ?lang=en."""
    request = _make_request("lang=en")
    response = await api_autonomous(request)
    data = json.loads(response.body)

    # Check first job is in English
    daily_research = next(j for j in data["jobs"] if j["id"] == "daily_research")
    assert daily_research["description"] == "PubMed research scan"
    assert daily_research["schedule"] == "every 2 days 07:00 UTC"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_lang_sk():
    """Should return Slovak descriptions by default."""
    request = _make_request()
    response = await api_autonomous(request)
    data = json.loads(response.body)

    daily_research = next(j for j in data["jobs"] if j["id"] == "daily_research")
    assert daily_research["description"] == "Prehľad výskumu PubMed"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", False)
async def test_autonomous_disabled():
    """Should return enabled=false with no jobs when disabled."""
    request = _make_request()
    response = await api_autonomous(request)
    data = json.loads(response.body)

    assert data["enabled"] is False
    assert "jobs" not in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_trigger_unknown():
    """Should return 400 for unknown task name."""
    request = _make_request("trigger=nonexistent_task")
    response = await api_autonomous(request)
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "error" in data


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_trigger_no_api_key():
    """Should return 500 when ANTHROPIC_API_KEY is not set."""
    with patch("oncoteam.config.ANTHROPIC_API_KEY", ""):
        request = _make_request("trigger=file_scan")
        response = await api_autonomous(request)
        data = json.loads(response.body)

    assert response.status_code == 500
    assert "ANTHROPIC_API_KEY" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_last_trigger_empty():
    """Should return no_trigger_yet when no task has been triggered."""
    import oncoteam.dashboard_api as mod

    mod._last_trigger_result = None
    request = _make_request("last_trigger=1")
    response = await api_autonomous(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "no_trigger_yet"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_has_cors():
    request = _make_request()
    response = await api_autonomous(request)
    assert response.headers["access-control-allow-origin"] == "https://dashboard.oncoteam.cloud"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_job_tool_mapping():
    """Verify specific job-to-tool mappings match the scheduler."""
    request = _make_request("lang=en")
    response = await api_autonomous(request)
    data = json.loads(response.body)

    jobs_map = {j["id"]: j["assigned_tool"] for j in data["jobs"]}

    assert jobs_map["daily_research"] == "search_pubmed"
    assert jobs_map["trial_monitor"] == "search_clinical_trials"
    assert jobs_map["pre_cycle_check"] == "pre_cycle_check"
    assert jobs_map["lab_sync"] == "analyze_labs"
    assert jobs_map["file_scan"] == "search_documents"
    assert jobs_map["weekly_briefing"] == "daily_briefing"
    assert jobs_map["medication_adherence_check"] == "search_documents"
