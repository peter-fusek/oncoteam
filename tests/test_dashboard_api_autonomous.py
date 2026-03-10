"""Tests for /api/autonomous endpoint."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from oncoteam.dashboard_api import api_autonomous


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)

    return FakeRequest(query_string)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.AUTONOMOUS_ENABLED", True)
async def test_autonomous_returns_jobs():
    """Should return 13 jobs with assigned_tool field."""
    request = _make_request()
    response = await api_autonomous(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["enabled"] is True
    assert "daily_cost" in data
    assert len(data["jobs"]) == 13
    assert data["job_count"] == 13


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
    assert daily_research["schedule"] == "daily 07:00 UTC"


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
async def test_autonomous_has_cors():
    request = _make_request()
    response = await api_autonomous(request)
    assert response.headers["access-control-allow-origin"] == "*"


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
    assert jobs_map["medication_adherence_check"] == "log_session_note"
