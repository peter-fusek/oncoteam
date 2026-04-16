"""Tests for api_health_deep, api_patients, and api_preventive_care endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam.api_admin import api_patients
from oncoteam.dashboard_api import api_health_deep, api_preventive_care


def _make_request(query_string: str = "") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": "https://dashboard.oncoteam.cloud"})

    return FakeRequest(query_string)


# ── api_health_deep ──────────────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.search_activity_log",
    new_callable=AsyncMock,
)
async def test_health_deep_ok(mock_search):
    """Should return 'ok' when oncofiles is reachable."""
    mock_search.return_value = []
    with patch("oncoteam.scheduler._standalone_scheduler", None):
        response = await api_health_deep(_make_request())
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["backend"] == "ok"
    assert data["oncofiles"] == "ok"
    assert "version" in data
    assert "memory_rss_mb" in data


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.search_activity_log",
    new_callable=AsyncMock,
    side_effect=Exception("connection refused"),
)
async def test_health_deep_degraded_on_oncofiles_error(mock_search):
    """Should return 'degraded' when oncofiles is unreachable."""
    with patch("oncoteam.scheduler._standalone_scheduler", None):
        response = await api_health_deep(_make_request())
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert "error" in data["oncofiles"]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.search_activity_log",
    new_callable=AsyncMock,
)
async def test_health_deep_includes_scheduler(mock_search):
    """Should include scheduler status when running."""
    mock_search.return_value = []
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    mock_job = MagicMock()
    mock_job.id = "daily_research"
    mock_job.next_run_time = None
    mock_scheduler.get_jobs.return_value = [mock_job]

    with patch("oncoteam.scheduler._standalone_scheduler", mock_scheduler):
        response = await api_health_deep(_make_request())
    data = json.loads(response.body)

    assert data["scheduler"]["running"] is True
    assert data["scheduler"]["job_count"] == 1


# ── api_patients ─────────────────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.api_admin.oncofiles_client.list_patients",
    new_callable=AsyncMock,
)
async def test_patients_returns_list(mock_list):
    """Should return patient list from oncofiles."""
    mock_list.return_value = {
        "patients": [
            {"slug": "q1b", "name": "Erika", "patient_type": "oncology"},
            {"slug": "e5g", "name": "Peter", "patient_type": "general"},
        ]
    }
    response = await api_patients(_make_request())
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["patients"]) == 2
    assert data["patients"][0]["slug"] == "q1b"


@pytest.mark.anyio
@patch(
    "oncoteam.api_admin.oncofiles_client.list_patients",
    new_callable=AsyncMock,
    side_effect=Exception("oncofiles down"),
)
async def test_patients_falls_back_to_local(mock_list):
    """Should fall back to local registry when oncofiles fails."""
    response = await api_patients(_make_request())
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["source"] == "local"
    assert len(data["patients"]) >= 1  # At least q1b from registry


# ── api_preventive_care ──────────────────────────────────


@pytest.mark.anyio
async def test_preventive_care_rejects_oncology_patient():
    """Should return 400 for oncology patients (q1b)."""
    response = await api_preventive_care(_make_request("patient_id=q1b"))
    data = json.loads(response.body)

    assert response.status_code == 400
    assert "general health" in data["error"].lower()


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.call_oncofiles",
    new_callable=AsyncMock,
)
async def test_preventive_care_returns_screenings_for_general_patient(mock_call):
    """Should return screening data for general health patients (e5g)."""
    mock_call.return_value = {
        "screenings": [{"name": "Colonoscopy", "status": "due", "next_due": "2026-06-01"}]
    }
    response = await api_preventive_care(_make_request("patient_id=e5g"))
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "screenings" in data
