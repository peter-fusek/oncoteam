"""Tests for WhatsApp internal API endpoints (#27, #26)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_log_whatsapp, api_whatsapp_chat


class FakeRequest:
    def __init__(self, method: str = "POST", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams("")
        self._body = body
        self.headers = {}

    async def body(self) -> bytes:
        return self._body


# ── /api/internal/log-whatsapp ─────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.log_conversation",
    new_callable=AsyncMock,
)
async def test_log_whatsapp_success(mock_log):
    mock_log.return_value = {"id": 42}
    body = json.dumps(
        {
            "phone": "+421900111222",
            "user_message": "labky",
            "bot_response": "ANC: 3200, PLT: 180000",
        }
    ).encode()
    request = FakeRequest(body=body)
    response = await api_log_whatsapp(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["logged"] is True
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args[1]
    assert call_kwargs["entry_type"] == "whatsapp"
    assert "sys:whatsapp" in call_kwargs["tags"]
    assert "+421900111222" in call_kwargs["content"]


@pytest.mark.anyio
@patch(
    "oncoteam.dashboard_api.oncofiles_client.log_conversation",
    new_callable=AsyncMock,
    side_effect=RuntimeError("connection failed"),
)
async def test_log_whatsapp_error_returns_502(mock_log):
    body = json.dumps({"phone": "x", "user_message": "hi", "bot_response": "bye"}).encode()
    request = FakeRequest(body=body)
    response = await api_log_whatsapp(request)
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "error" in data


@pytest.mark.anyio
async def test_log_whatsapp_defaults_phone():
    """Missing phone defaults to 'unknown'."""
    with patch(
        "oncoteam.dashboard_api.oncofiles_client.log_conversation",
        new_callable=AsyncMock,
    ) as mock_log:
        mock_log.return_value = {"id": 1}
        body = json.dumps({"user_message": "test"}).encode()
        request = FakeRequest(body=body)
        response = await api_log_whatsapp(request)
        data = json.loads(response.body)

        assert data["logged"] is True
        call_kwargs = mock_log.call_args[1]
        assert "unknown" in call_kwargs["content"]


# ── /api/internal/whatsapp-chat ────────────────────


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.dashboard_api.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.dashboard_api.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_success(mock_run, _mock_cb):
    mock_run.return_value = {"response": "Lab values look normal.", "cost": 0.002}
    body = json.dumps({"message": "Ako su labky?", "phone": "+421", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["response"] == "Lab values look normal."
    assert data["cost"] == 0.002
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["task_name"] == "whatsapp_chat"
    assert call_kwargs["max_turns"] == 3


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "open"},
)
async def test_whatsapp_chat_circuit_breaker_open(_mock_cb):
    """Should return clear message when oncofiles is down instead of wasting API call."""
    body = json.dumps({"message": "record Clexane", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "nedostupná" in data["response"]
    assert data["cost"] == 0


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "")
async def test_whatsapp_chat_no_api_key():
    body = json.dumps({"message": "hello"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 500
    assert "not configured" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.dashboard_api.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.dashboard_api.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_empty_response_gives_fallback(mock_run, _mock_cb):
    mock_run.return_value = {"response": "", "cost": 0}
    body = json.dumps({"message": "?", "lang": "en"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "help" in data["response"].lower()


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.dashboard_api.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.dashboard_api.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_truncates_long_response(mock_run, _mock_cb):
    mock_run.return_value = {"response": "a" * 2000, "cost": 0}
    body = json.dumps({"message": "tell me everything"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert len(data["response"]) <= 1500


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.dashboard_api.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.dashboard_api.run_autonomous_task",
    new_callable=AsyncMock,
    side_effect=RuntimeError("API down"),
)
async def test_whatsapp_chat_error_returns_fallback(mock_run, _mock_cb):
    body = json.dumps({"message": "test"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "help" in data["response"].lower() or "Error" in data["response"]


@pytest.mark.anyio
@patch("oncoteam.dashboard_api.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.dashboard_api.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.dashboard_api.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.dashboard_api.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_sk_fallback_message(mock_run, _mock_cb):
    """Slovak fallback when response is empty."""
    mock_run.return_value = {"response": "", "cost": 0}
    body = json.dumps({"message": "?", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert "pomoc" in data["response"].lower() or "Prepáčte" in data["response"]
