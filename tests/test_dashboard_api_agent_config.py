"""Tests for /api/agents/{id}/config endpoint (#92 Phase 4)."""

from __future__ import annotations

import json

import pytest

from oncoteam.dashboard_api import api_agent_config


def _make_request(path_params: dict | None = None, query_string: str = "patient_id=q1b") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, params: dict | None, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})
            self.path_params = params or {}

    return FakeRequest(path_params, query_string)


@pytest.mark.anyio
async def test_agent_config_returns_full_config():
    """Should return full agent config including prompt_template."""
    request = _make_request(path_params={"id": "tumor_marker_review"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["id"] == "tumor_marker_review"
    assert "prompt_template" in data
    assert "CEA" in data["prompt_template"]
    assert data["category"] == "clinical"
    assert data["cooldown_hours"] == 0.5


@pytest.mark.anyio
async def test_agent_config_not_found():
    """Should return 404 for unknown agent."""
    request = _make_request(path_params={"id": "nonexistent_agent"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 404
    assert "error" in data


@pytest.mark.anyio
async def test_agent_config_static_prompt():
    """Static-prompt agents should have a real prompt template."""
    request = _make_request(path_params={"id": "lab_sync"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "store_lab_values" in data["prompt_template"]
    assert not data["prompt_template"].startswith("[Dynamic")


@pytest.mark.anyio
async def test_agent_config_dynamic_prompt():
    """Dynamic-prompt agents should have a descriptive marker."""
    request = _make_request(path_params={"id": "pre_cycle_check"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["prompt_template"].startswith("[Dynamic")


@pytest.mark.anyio
async def test_agent_config_file_scan_has_placeholder():
    """file_scan prompt should contain the {last_scan} placeholder."""
    request = _make_request(path_params={"id": "file_scan"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "{last_scan}" in data["prompt_template"]


@pytest.mark.anyio
async def test_agent_config_medication_has_placeholder():
    """medication_adherence_check prompt should contain the {today} placeholder."""
    request = _make_request(path_params={"id": "medication_adherence_check"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "{today}" in data["prompt_template"]


@pytest.mark.anyio
async def test_agent_config_includes_all_fields():
    """Config response should include all AgentConfig fields."""
    request = _make_request(path_params={"id": "toxicity_extraction"})
    response = await api_agent_config(request)
    data = json.loads(response.body)

    expected_fields = {
        "id",
        "name",
        "description",
        "category",
        "model",
        "schedule_type",
        "schedule_params",
        "cooldown_hours",
        "max_turns",
        "whatsapp_enabled",
        "enabled",
        "prompt_template",
        "assigned_tool",
        "schedule_display",
        "misfire_grace_time",
    }
    assert expected_fields.issubset(data.keys()), f"Missing fields: {expected_fields - data.keys()}"
