"""Tests for dashboard API endpoints (GET /api/*)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import (
    VERSION,
    _build_external_url,
    _extract_list,
    _is_test_entry,
    api_activity,
    api_cors_preflight,
    api_patient,
    api_research,
    api_sessions,
    api_stats,
    api_status,
    api_timeline,
)

# ── Helpers ───────────────────────────────────────


def _make_request(
    path: str = "/api/test",
    query_string: str = "",
    origin: str = "https://oncoteam-dashboard.onrender.com",
) -> object:
    """Create a minimal Starlette-like Request stub."""
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, query: str, origin: str):
            self.query_params = QueryParams(query)
            self.headers = Headers({"origin": origin} if origin else {})

    return FakeRequest(query_string, origin)


# ── /api/status ───────────────────────────────────


@pytest.mark.anyio
async def test_api_status_returns_ok():
    request = _make_request("/api/status")
    response = await api_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["server"] == "oncoteam"
    assert data["version"] == VERSION
    assert "session_id" in data
    assert data["tools_count"] == 20
    assert isinstance(data["tools"], list)


@pytest.mark.anyio
async def test_api_status_has_cors_headers():
    request = _make_request("/api/status")
    response = await api_status(request)
    assert response.headers["access-control-allow-origin"] == "https://oncoteam-dashboard.onrender.com"
    assert "GET" in response.headers["access-control-allow-methods"]


# ── /api/activity ─────────────────────────────────


MOCK_ACTIVITY_ENTRIES = {
    "entries": [
        {
            "tool_name": "search_pubmed",
            "status": "ok",
            "duration_ms": 120,
            "created_at": "2026-03-06T10:00:00Z",
            "input_summary": "query='KRAS'",
            "output_summary": "3 articles",
            "error_message": None,
        },
        {
            "tool_name": "daily_briefing",
            "status": "ok",
            "duration_ms": 2500,
            "created_at": "2026-03-06T09:00:00Z",
            "input_summary": "",
            "output_summary": "5 articles, 3 trials",
            "error_message": None,
        },
    ]
}


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_returns_entries(mock_search):
    mock_search.return_value = MOCK_ACTIVITY_ENTRIES
    request = _make_request("/api/activity")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 2
    assert data["entries"][0]["tool"] == "search_pubmed"
    assert data["entries"][0]["duration_ms"] == 120
    mock_search.assert_called_once_with(agent_id="oncoteam", limit=50)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_with_limit(mock_search):
    mock_search.return_value = {"entries": []}
    request = _make_request("/api/activity", "limit=5")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert data["total"] == 0
    mock_search.assert_called_once_with(agent_id="oncoteam", limit=5)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_handles_oncofiles_error(mock_search):
    mock_search.side_effect = Exception("connection refused")
    request = _make_request("/api/activity")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "error" in data
    assert data["entries"] == []


# ── /api/stats ────────────────────────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_stats_returns_data(mock_log):
    mock_log.return_value = {
        "entries": [
            {"tool_name": "search_pubmed", "status": "success", "duration_ms": 200},
            {"tool_name": "search_pubmed", "status": "error", "duration_ms": 100},
            {"tool_name": "daily_briefing", "status": "success", "duration_ms": 500},
        ]
    }
    request = _make_request("/api/stats")
    response = await api_stats(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert len(data["stats"]) == 2
    pubmed = next(s for s in data["stats"] if s["tool_name"] == "search_pubmed")
    assert pubmed["count"] == 2
    assert pubmed["error_count"] == 1


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_stats_filters_test_entries(mock_log):
    mock_log.return_value = {
        "entries": [
            {"tool_name": "search_pubmed", "status": "success", "duration_ms": 200},
            {
                "tool_name": "search_pubmed", "status": "success",
                "duration_ms": 100, "tags": ["e2e-test"],
            },
        ]
    }
    request = _make_request("/api/stats")
    response = await api_stats(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    pubmed = data["stats"][0]
    assert pubmed["count"] == 1  # test entry filtered out


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_stats_handles_error(mock_log):
    mock_log.side_effect = Exception("timeout")
    request = _make_request("/api/stats")
    response = await api_stats(request)

    assert response.status_code == 502


# ── /api/timeline ─────────────────────────────────


MOCK_EVENTS = {
    "events": [
        {
            "id": 1,
            "event_date": "2026-02-14",
            "event_type": "chemo_cycle",
            "title": "mFOLFOX6 C1",
            "notes": "First cycle",
        },
    ]
}


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_api_timeline_returns_events(mock_list):
    mock_list.return_value = MOCK_EVENTS
    request = _make_request("/api/timeline")
    response = await api_timeline(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["events"][0]["type"] == "chemo_cycle"
    assert data["events"][0]["title"] == "mFOLFOX6 C1"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_api_timeline_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = _make_request("/api/timeline")
    response = await api_timeline(request)

    assert response.status_code == 502


# ── /api/patient ──────────────────────────────────


@pytest.mark.anyio
async def test_api_patient_returns_profile():
    request = _make_request("/api/patient", query_string="lang=en")
    response = await api_patient(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["name"] == "Erika Fusekova"
    assert data["diagnosis_code"] == "C18.7"
    assert data["biomarkers"]["KRAS"] == "mutant G12S (c.34G>A)"
    assert data["staging"].startswith("IV (liver mets, peritoneal carcinomatosis")
    assert isinstance(data["diagnosis_date"], str)


@pytest.mark.anyio
async def test_api_patient_has_cors():
    request = _make_request("/api/patient")
    response = await api_patient(request)
    assert response.headers["access-control-allow-origin"] == "https://oncoteam-dashboard.onrender.com"


# ── /api/research ─────────────────────────────────


MOCK_RESEARCH = {
    "entries": [
        {
            "id": 10,
            "source": "pubmed",
            "external_id": "12345678",
            "title": "KRAS G12S study",
            "summary": "A study...",
            "created_at": "2026-03-06T10:00:00Z",
        },
    ]
}


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_api_research_returns_entries(mock_list):
    mock_list.return_value = MOCK_RESEARCH
    request = _make_request("/api/research")
    response = await api_research(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    entry = data["entries"][0]
    assert entry["source"] == "pubmed"
    assert entry["relevance"] == "high"  # "KRAS G12S" matches patient
    assert entry["relevance_reason"]
    mock_list.assert_called_once_with(source=None, limit=20)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_api_research_relevance_sorting(mock_list):
    """Research entries are sorted: high > medium > low > not_applicable."""
    mock_list.return_value = {
        "entries": [
            {"id": 1, "source": "pubmed", "external_id": "1",
             "title": "General oncology review", "created_at": "2026-03-01"},
            {"id": 2, "source": "pubmed", "external_id": "2",
             "title": "Cetuximab in mCRC", "created_at": "2026-03-02"},
            {"id": 3, "source": "clinicaltrials", "external_id": "NCT001",
             "title": "FOLFOX in metastatic colorectal cancer",
             "created_at": "2026-03-03"},
        ]
    }
    request = _make_request("/api/research")
    response = await api_research(request)
    data = json.loads(response.body)

    scores = [e["relevance"] for e in data["entries"]]
    # FOLFOX mCRC = high, cetuximab = not_applicable, general = low
    assert scores[0] == "high"
    assert scores[-1] in ("low", "not_applicable")


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_api_research_false_hope_detection(mock_list):
    """Anti-EGFR and G12C studies are flagged as not_applicable."""
    mock_list.return_value = {
        "entries": [
            {"id": 1, "source": "pubmed", "external_id": "1",
             "title": "Sotorasib in KRAS G12C CRC",
             "created_at": "2026-03-01"},
            {"id": 2, "source": "pubmed", "external_id": "2",
             "title": "Panitumumab in wild-type KRAS CRC",
             "created_at": "2026-03-02"},
        ]
    }
    request = _make_request("/api/research")
    response = await api_research(request)
    data = json.loads(response.body)

    for entry in data["entries"]:
        assert entry["relevance"] == "not_applicable"
        assert entry["relevance_reason"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_api_research_with_source_filter(mock_list):
    mock_list.return_value = {"entries": []}
    request = _make_request("/api/research", "source=clinicaltrials&limit=5")
    response = await api_research(request)
    data = json.loads(response.body)

    assert data["total"] == 0
    mock_list.assert_called_once_with(source="clinicaltrials", limit=5)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_research_entries", new_callable=AsyncMock)
async def test_api_research_handles_error(mock_list):
    mock_list.side_effect = Exception("fail")
    request = _make_request("/api/research")
    response = await api_research(request)

    assert response.status_code == 502


# ── /api/sessions ─────────────────────────────────


MOCK_SESSIONS = {
    "entries": [
        {
            "id": 5,
            "title": "Session: Reviewed lab results",
            "content": "Discussed CBC trends and SII calculation.",
            "created_at": "2026-03-06T12:00:00Z",
            "tags": "session,sid:20260306-abc123",
        },
    ]
}


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_sessions_returns_entries(mock_search):
    mock_search.return_value = MOCK_SESSIONS
    request = _make_request("/api/sessions")
    response = await api_sessions(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["sessions"][0]["title"] == "Session: Reviewed lab results"
    mock_search.assert_called_once_with(entry_type="session_summary", limit=20)


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_sessions_handles_error(mock_search):
    mock_search.side_effect = Exception("fail")
    request = _make_request("/api/sessions")
    response = await api_sessions(request)

    assert response.status_code == 502


# ── CORS preflight ────────────────────────────────


# ── _extract_list helper ──────────────────────────


def test_extract_list_from_list():
    assert _extract_list([{"a": 1}], "entries") == [{"a": 1}]


def test_extract_list_from_dict_with_key():
    assert _extract_list({"events": [{"b": 2}]}, "events") == [{"b": 2}]


def test_extract_list_from_dict_with_entries_fallback():
    assert _extract_list({"entries": [{"c": 3}]}, "items") == [{"c": 3}]


def test_extract_list_from_empty():
    assert _extract_list({}, "entries") == []
    assert _extract_list("text", "entries") == []


# ── _build_external_url helper ───────────────────


def test_build_external_url_pubmed():
    assert _build_external_url("pubmed", "12345678") == "https://pubmed.ncbi.nlm.nih.gov/12345678/"


def test_build_external_url_clinicaltrials():
    assert (
        _build_external_url("clinicaltrials", "NCT00001234")
        == "https://clinicaltrials.gov/study/NCT00001234"
    )


def test_build_external_url_no_source():
    assert _build_external_url("", "12345678") is None
    assert _build_external_url("pubmed", "") is None


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_api_timeline_handles_list_response(mock_list):
    """Oncofiles may return a plain list instead of {events: [...]}."""
    mock_list.return_value = [
        {
            "id": 1,
            "event_date": "2026-02-14",
            "event_type": "chemo_cycle",
            "title": "mFOLFOX6 C1",
            "notes": "First cycle",
        },
    ]
    request = _make_request("/api/timeline")
    response = await api_timeline(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["events"][0]["title"] == "mFOLFOX6 C1"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_handles_list_response(mock_search):
    """Oncofiles may return a plain list instead of {entries: [...]}."""
    mock_search.return_value = [
        {
            "tool_name": "search_pubmed",
            "status": "ok",
            "duration_ms": 120,
            "created_at": "2026-03-06T10:00:00Z",
            "input_summary": "query='KRAS'",
            "output_summary": "3 articles",
            "error_message": None,
        },
    ]
    request = _make_request("/api/activity")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["entries"][0]["tool"] == "search_pubmed"


# ── CORS preflight ────────────────────────────────


@pytest.mark.anyio
async def test_cors_preflight_returns_headers():
    request = _make_request("/api/status")
    response = await api_cors_preflight(request)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://oncoteam-dashboard.onrender.com"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]


# ── Test data filtering ──────────────────────────


def test_is_test_entry_detects_e2e_title():
    assert _is_test_entry({"title": "e2e-test-abc123"})
    assert _is_test_entry({"title": "E2E test research something"})


def test_is_test_entry_detects_testovacia():
    assert _is_test_entry({"title": "Testovacia konzultacia"})


def test_is_test_entry_detects_e2e_tool():
    assert _is_test_entry({"tool_name": "e2e_test"})


def test_is_test_entry_detects_e2e_agent():
    assert _is_test_entry({"agent_id": "oncoteam-e2e"})


def test_is_test_entry_detects_e2e_tags():
    assert _is_test_entry({"tags": ["e2e-test"]})
    assert _is_test_entry({"tags": "e2e-test,other"})


def test_is_test_entry_passes_real_data():
    assert not _is_test_entry({"title": "mFOLFOX6 C1"})
    assert not _is_test_entry({"tool_name": "search_pubmed"})
    assert not _is_test_entry({"agent_id": "oncoteam"})
    assert not _is_test_entry({})


# ── API auth ─────────────────────────────────────


class TestApiAuth:
    def test_no_key_configured_allows_all(self):
        from oncoteam.dashboard_api import _check_api_auth

        request = _make_request()
        with patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", ""):
            assert _check_api_auth(request) is None

    def test_valid_bearer_token(self):
        from starlette.datastructures import Headers, QueryParams

        from oncoteam.dashboard_api import _check_api_auth

        class AuthRequest:
            query_params = QueryParams("")
            headers = Headers({"authorization": "Bearer test-secret-123"})

        with patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", "test-secret-123"):
            assert _check_api_auth(AuthRequest()) is None

    def test_invalid_bearer_token(self):
        from starlette.datastructures import Headers, QueryParams

        from oncoteam.dashboard_api import _check_api_auth

        class AuthRequest:
            query_params = QueryParams("")
            headers = Headers({"authorization": "Bearer wrong-key"})

        with patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", "test-secret-123"):
            result = _check_api_auth(AuthRequest())
            assert result is not None
            assert result.status_code == 401

    def test_valid_query_param_key(self):
        from starlette.datastructures import Headers, QueryParams

        from oncoteam.dashboard_api import _check_api_auth

        class AuthRequest:
            query_params = QueryParams("key=test-secret-123")
            headers = Headers({})

        with patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", "test-secret-123"):
            assert _check_api_auth(AuthRequest()) is None

    def test_missing_key_returns_401(self):
        from starlette.datastructures import Headers, QueryParams

        from oncoteam.dashboard_api import _check_api_auth

        class AuthRequest:
            query_params = QueryParams("")
            headers = Headers({})

        with patch("oncoteam.dashboard_api.DASHBOARD_API_KEY", "test-secret-123"):
            result = _check_api_auth(AuthRequest())
            assert result is not None
            assert result.status_code == 401


class TestCorsOrigin:
    def test_allowed_origin(self):
        from oncoteam.dashboard_api import _get_cors_origin

        request = _make_request()
        assert _get_cors_origin(request) == "https://oncoteam-dashboard.onrender.com"

    def test_localhost_allowed(self):
        from oncoteam.dashboard_api import _get_cors_origin

        request = _make_request(origin="http://localhost:3000")
        assert _get_cors_origin(request) == "http://localhost:3000"

    def test_unknown_origin_rejected(self):
        from oncoteam.dashboard_api import _get_cors_origin

        request = _make_request(origin="https://evil.example.com")
        assert _get_cors_origin(request) == ""


MOCK_ACTIVITY_WITH_TEST = [
    {
        "tool_name": "search_pubmed",
        "status": "ok",
        "duration_ms": 120,
        "created_at": "2026-03-06T10:00:00Z",
        "input_summary": "",
        "output_summary": "",
        "error_message": None,
    },
    {
        "tool_name": "e2e_test",
        "status": "ok",
        "duration_ms": 42,
        "created_at": "2026-03-06T09:00:00Z",
        "input_summary": "test",
        "output_summary": "test",
        "error_message": None,
    },
]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_filters_test_data_by_default(mock_search):
    mock_search.return_value = MOCK_ACTIVITY_WITH_TEST
    request = _make_request("/api/activity")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert data["total"] == 1
    assert data["entries"][0]["tool"] == "search_pubmed"


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_activity_log", new_callable=AsyncMock)
async def test_api_activity_shows_test_data_when_requested(mock_search):
    mock_search.return_value = MOCK_ACTIVITY_WITH_TEST
    request = _make_request("/api/activity", "show_test=true")
    response = await api_activity(request)
    data = json.loads(response.body)

    assert data["total"] == 2


MOCK_TIMELINE_WITH_TEST = [
    {
        "id": 1,
        "event_date": "2026-02-14",
        "event_type": "chemo_cycle",
        "title": "mFOLFOX6 C1",
        "notes": "Real",
    },
    {
        "id": 2,
        "event_date": "2026-03-05",
        "event_type": "consultation",
        "title": "E2E test event abc",
        "notes": "Test",
    },
]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.list_treatment_events", new_callable=AsyncMock)
async def test_api_timeline_filters_test_data(mock_list):
    mock_list.return_value = MOCK_TIMELINE_WITH_TEST
    request = _make_request("/api/timeline")
    response = await api_timeline(request)
    data = json.loads(response.body)

    assert data["total"] == 1
    assert data["events"][0]["title"] == "mFOLFOX6 C1"


MOCK_SESSIONS_WITH_TEST = [
    {
        "id": 5,
        "title": "Session: Lab review",
        "content": "Real session",
        "created_at": "2026-03-06T12:00:00Z",
        "tags": ["session"],
    },
    {
        "id": 6,
        "title": "e2e-test-session",
        "content": "Test",
        "created_at": "2026-03-06T11:00:00Z",
        "tags": ["e2e-test"],
    },
]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.oncofiles_client.search_conversations", new_callable=AsyncMock)
async def test_api_sessions_filters_test_data(mock_search):
    mock_search.return_value = MOCK_SESSIONS_WITH_TEST
    request = _make_request("/api/sessions")
    response = await api_sessions(request)
    data = json.loads(response.body)

    assert data["total"] == 1
    assert data["sessions"][0]["title"] == "Session: Lab review"
