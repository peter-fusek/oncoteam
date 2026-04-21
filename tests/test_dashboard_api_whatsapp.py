"""Tests for WhatsApp internal API endpoints (#27, #26)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_log_whatsapp, api_whatsapp_chat, api_whatsapp_status


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
    "oncoteam.api_whatsapp.oncofiles_client.log_conversation",
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
    "oncoteam.api_whatsapp.oncofiles_client.log_conversation",
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
        "oncoteam.api_whatsapp.oncofiles_client.log_conversation",
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
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_success(mock_run, _mock_save, _mock_load, _mock_cb):
    mock_run.return_value = {"response": "Lab values look normal.", "cost": 0.002}
    body = json.dumps({"message": "Ako su labky?", "phone": "+421", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["response"].startswith("Lab values look normal.")
    # #382: every WA reply ends with a physician-verifies disclaimer
    assert "overí lekár" in data["response"]
    assert data["cost"] == 0.002
    assert data["thread_length"] == 1
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["task_name"] == "whatsapp_chat"
    assert call_kwargs["max_turns"] == 5


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch("oncoteam.api_whatsapp.run_autonomous_task", new_callable=AsyncMock)
async def test_whatsapp_chat_english_gets_english_disclaimer(
    mock_run, _mock_save, _mock_load, _mock_cb
):
    """EN replies get the English disclaimer; SK replies get the Slovak one (#382)."""
    mock_run.return_value = {"response": "Your ANC is within safe range.", "cost": 0.001}
    body = json.dumps({"message": "How are my labs?", "lang": "en"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert "physician verifies" in data["response"]
    assert "overí lekár" not in data["response"]


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch("oncoteam.api_whatsapp.run_autonomous_task", new_callable=AsyncMock)
async def test_whatsapp_chat_does_not_duplicate_disclaimer(
    mock_run, _mock_save, _mock_load, _mock_cb
):
    """If the model already included a physician-verifies line, don't double it up."""
    mock_run.return_value = {
        "response": "ANC is normal. Informatívne, overí lekár.",
        "cost": 0.001,
    }
    body = json.dumps({"message": "labky", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    # Only one occurrence — the model's own line is kept, no second line appended
    assert data["response"].count("overí lekár") == 1


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
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
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "")
async def test_whatsapp_chat_no_api_key():
    body = json.dumps({"message": "hello"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 500
    assert "not configured" in data["error"]


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_empty_response_gives_fallback(
    mock_run, _mock_save, _mock_load, _mock_cb
):
    mock_run.return_value = {"response": "", "cost": 0}
    body = json.dumps({"message": "?", "lang": "en"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "help" in data["response"].lower()


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_truncates_long_response(mock_run, _mock_save, _mock_load, _mock_cb):
    mock_run.return_value = {"response": "a" * 2000, "cost": 0}
    body = json.dumps({"message": "tell me everything"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert len(data["response"]) <= 1500


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
    side_effect=RuntimeError("API down"),
)
async def test_whatsapp_chat_error_returns_fallback(mock_run, _mock_save, _mock_load, _mock_cb):
    body = json.dumps({"message": "test"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert "help" in data["response"].lower() or "Error" in data["response"]


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch("oncoteam.api_whatsapp._load_wa_thread", new_callable=AsyncMock, return_value=[])
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_sk_fallback_message(mock_run, _mock_save, _mock_load, _mock_cb):
    """Slovak fallback when response is empty."""
    mock_run.return_value = {"response": "", "cost": 0}
    body = json.dumps({"message": "?", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert "pomoc" in data["response"].lower() or "Prepáčte" in data["response"]


@pytest.mark.anyio
@patch("oncoteam.api_whatsapp.ANTHROPIC_API_KEY", "test-key")
@patch("oncoteam.api_whatsapp.AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.api_whatsapp._load_wa_thread",
    new_callable=AsyncMock,
    return_value=[{"user": "Ake su labky?", "assistant": "ANC 3200, PLT 180k."}],
)
@patch("oncoteam.api_whatsapp._save_wa_thread", new_callable=AsyncMock)
@patch(
    "oncoteam.api_whatsapp.run_autonomous_task",
    new_callable=AsyncMock,
)
async def test_whatsapp_chat_includes_thread_context(mock_run, _mock_save, _mock_load, _mock_cb):
    """Conversation thread history is included in prompt."""
    mock_run.return_value = {"response": "PLT is 180k, within range.", "cost": 0.001}
    body = json.dumps({"message": "A trombocyty?", "phone": "+421", "lang": "sk"}).encode()
    request = FakeRequest(body=body)
    response = await api_whatsapp_chat(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["thread_length"] == 2
    # Verify prompt contains conversation history
    prompt = mock_run.call_args[0][0]
    assert "Previous conversation" in prompt
    assert "Ake su labky?" in prompt


# ── /api/whatsapp/status ─────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.search_conversations",
    new_callable=AsyncMock,
    return_value={"entries": [{"id": 1}, {"id": 2}, {"id": 3}]},
)
@patch("oncoteam.api_whatsapp._approved_phones_loaded", True)
@patch("oncoteam.api_whatsapp._approved_phones", {"+421900111222", "+421900333444"})
@patch("oncoteam.api_whatsapp._phone_patient_map", {"+421900111222": "q1b"})
async def test_whatsapp_status_ok(_mock_conv, _mock_cb):
    request = FakeRequest(method="GET")
    response = await api_whatsapp_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["approved_phones"] == 2
    assert data["recent_conversations"] == 3
    assert data["circuit_breaker_state"] == "closed"
    assert data["phone_patient_map"] == {"+421900111222": "q1b"}


@pytest.mark.anyio
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "open"},
)
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.search_conversations",
    new_callable=AsyncMock,
    side_effect=RuntimeError("oncofiles down"),
)
@patch("oncoteam.api_whatsapp._approved_phones_loaded", True)
@patch("oncoteam.api_whatsapp._approved_phones", set())
@patch("oncoteam.api_whatsapp._phone_patient_map", {})
async def test_whatsapp_status_degraded(_mock_conv, _mock_cb):
    request = FakeRequest(method="GET")
    response = await api_whatsapp_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert data["approved_phones"] == 0
    assert data["recent_conversations"] == 0


@pytest.mark.anyio
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.get_circuit_breaker_status",
    return_value={"state": "closed"},
)
@patch(
    "oncoteam.api_whatsapp.oncofiles_client.search_conversations",
    new_callable=AsyncMock,
    return_value={"entries": [{"id": 1}, {"id": 2}]},
)
@patch(
    "oncoteam.api_admin._load_access_rights",
    new_callable=AsyncMock,
    return_value={
        "peter": {"phone": "+421903124356", "roles": ["advocate", "admin"]},
        "physician_zm": {"phone": "+421905000000", "roles": ["physician"]},
        "noop_entry_without_phone": {"roles": ["viewer"]},
    },
)
@patch("oncoteam.api_whatsapp._approved_phones_loaded", True)
@patch("oncoteam.api_whatsapp._approved_phones", set())
@patch("oncoteam.api_whatsapp._phone_patient_map", {})
async def test_whatsapp_status_counts_role_map_phones(_mock_load_rm, _mock_conv, _mock_cb):
    """#379 — role-map configured phones must show up in the approved count
    even when they never went through the explicit admin-approval flow.
    """
    request = FakeRequest(method="GET")
    response = await api_whatsapp_status(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    # Union of empty _approved_phones + 2 role_map phones (third entry has no phone)
    assert data["approved_phones"] == 2
    assert data["recent_conversations"] == 2

    # #419 — must pass entry_type="whatsapp", not the old query= typo
    _mock_conv.assert_called_once()
    call_kwargs = _mock_conv.call_args.kwargs
    assert call_kwargs.get("entry_type") == "whatsapp"
    assert "query" not in call_kwargs
