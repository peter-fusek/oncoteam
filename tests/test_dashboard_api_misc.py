"""Tests for api_resolve_patient, api_bug_report, api_trigger_agent endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam.dashboard_api import api_bug_report, api_resolve_patient, api_trigger_agent


def _make_post_request(body: dict, query_string: str = "patient_id=q1b") -> object:
    from starlette.datastructures import Headers, QueryParams

    class FakeRequest:
        def __init__(self, b: dict, query: str):
            self.query_params = QueryParams(query)
            self.headers = Headers(
                {
                    "origin": "https://dashboard.oncoteam.cloud",
                    "content-type": "application/json",
                    "content-length": str(len(json.dumps(b))),
                    "user-agent": "TestAgent/1.0",
                }
            )
            self._body = json.dumps(b).encode()

        async def body(self):
            return self._body

        async def json(self):
            return json.loads(self._body)

    return FakeRequest(body, query_string)


# ── api_resolve_patient ──────────────────────────────────


@pytest.mark.anyio
async def test_resolve_patient_empty_query_returns_null():
    """Should return null patient_id for empty query."""
    response = await api_resolve_patient(_make_post_request({"query": "", "allowed_ids": ["q1b"]}))
    data = json.loads(response.body)
    assert data["patient_id"] is None


@pytest.mark.anyio
async def test_resolve_patient_no_allowed_ids_returns_null():
    """Should return null for missing allowed_ids."""
    response = await api_resolve_patient(_make_post_request({"query": "erika", "allowed_ids": []}))
    data = json.loads(response.body)
    assert data["patient_id"] is None


@pytest.mark.anyio
async def test_resolve_patient_no_api_key_returns_error():
    """Should return error when ANTHROPIC_API_KEY is not set."""
    with patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", ""):
        response = await api_resolve_patient(
            _make_post_request({"query": "erika", "allowed_ids": ["q1b"]})
        )
    data = json.loads(response.body)
    assert data["patient_id"] is None
    assert "not configured" in data.get("error", "")


@pytest.mark.anyio
async def test_resolve_patient_claude_match():
    """Should return matched patient when Claude resolves a name."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="q1b")]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_resp)

    with (
        patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key"),
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
    ):
        response = await api_resolve_patient(
            _make_post_request({"query": "eriku", "allowed_ids": ["q1b", "e5g"]})
        )
    data = json.loads(response.body)
    assert data["patient_id"] == "q1b"


# ── api_bug_report ───────────────────────────────────────


@pytest.mark.anyio
async def test_bug_report_missing_description():
    """Should return 400 when description is empty."""
    response = await api_bug_report(_make_post_request({"description": ""}))
    data = json.loads(response.body)
    assert response.status_code == 400
    assert "description" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.github_client.create_issue", new_callable=AsyncMock)
async def test_bug_report_creates_issue(mock_create):
    """Should create a GitHub issue with the bug description."""
    mock_create.return_value = {"number": 999, "html_url": "https://github.com/test/999"}
    response = await api_bug_report(
        _make_post_request(
            {
                "description": "Button not working",
                "url": "https://dashboard.oncoteam.cloud/labs",
                "route": "/labs",
                "viewport": "1920x1080",
                "role": "advocate",
                "locale": "sk",
            }
        )
    )
    data = json.loads(response.body)
    assert response.status_code == 200
    assert data["created"] is True
    assert data["number"] == 999
    mock_create.assert_called_once()
    call_args = mock_create.call_args
    assert "Button not working" in call_args.kwargs.get("title", call_args[1].get("title", ""))


@pytest.mark.anyio
@patch(
    "oncoteam.github_client.create_issue",
    new_callable=AsyncMock,
    side_effect=Exception("GitHub API error"),
)
async def test_bug_report_github_error_returns_502(mock_create):
    """Should return 502 when GitHub issue creation fails."""
    response = await api_bug_report(
        _make_post_request({"description": "Something broke", "route": "/labs"})
    )
    data = json.loads(response.body)
    assert response.status_code == 502
    assert "error" in data


# ── api_trigger_agent ────────────────────────────────────


@pytest.mark.anyio
async def test_trigger_agent_unknown_agent():
    """Should return 400 for unknown agent_id."""
    response = await api_trigger_agent(_make_post_request({"agent_id": "nonexistent_agent"}))
    data = json.loads(response.body)
    assert response.status_code == 400
    assert "Unknown agent" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.api_webhooks.oncofiles_client.set_agent_state", new_callable=AsyncMock)
async def test_trigger_agent_success(mock_set):
    """Should trigger a known agent and return success."""
    mock_set.return_value = {}

    # Mock the task function
    mock_func = AsyncMock()
    mock_task_functions = {"daily_research": mock_func}

    with patch("oncoteam.scheduler._get_task_functions", return_value=mock_task_functions):
        response = await api_trigger_agent(_make_post_request({"agent_id": "daily_research"}))
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "triggered"
    assert data["agent_id"] == "daily_research"
