"""Tests for /api/internal/whatsapp-voice endpoint."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from oncoteam.dashboard_api import api_whatsapp_voice


class FakeRequest:
    def __init__(self, method: str = "POST", body: bytes = b""):
        from starlette.datastructures import QueryParams

        self.method = method
        self.query_params = QueryParams("")
        self._body = body
        self.headers = {}

    async def body(self) -> bytes:
        return self._body


def _make_request(body_dict: dict) -> FakeRequest:
    return FakeRequest(body=json.dumps(body_dict).encode())


# ── Success ───────────────────────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.whisper_client.transcribe_audio",
    new_callable=AsyncMock,
)
async def test_voice_endpoint_success(mock_transcribe):
    mock_transcribe.return_value = {
        "text": "labky cea",
        "duration_s": 3.5,
        "cost": 0.00035,
        "lang": "sk",
    }
    audio_b64 = base64.b64encode(b"\x00" * 2000).decode()
    req = _make_request(
        {
            "audio_base64": audio_b64,
            "content_type": "audio/ogg",
            "patient_id": "q1b",
        }
    )
    response = await api_whatsapp_voice(req)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["text"] == "labky cea"
    assert data["duration_s"] == 3.5
    mock_transcribe.assert_called_once()


# ── Missing audio ─────────────────────────────────────


@pytest.mark.anyio
async def test_voice_endpoint_missing_audio():
    req = _make_request({"content_type": "audio/ogg"})
    response = await api_whatsapp_voice(req)
    assert response.status_code == 400
    data = json.loads(response.body)
    assert "Missing audio_base64" in data["error"]


# ── Invalid base64 ────────────────────────────────────


@pytest.mark.anyio
async def test_voice_endpoint_invalid_base64():
    # Sprint 100 / #440 Pattern C — patient_id required; supply here so the
    # test exercises the downstream base64 validation, not the tenant-scope gate.
    req = _make_request({"audio_base64": "not-valid-base64!!!", "patient_id": "q1b"})
    response = await api_whatsapp_voice(req)
    assert response.status_code == 400
    data = json.loads(response.body)
    assert "Invalid base64" in data["error"]


# ── Audio too short ───────────────────────────────────


@pytest.mark.anyio
async def test_voice_endpoint_audio_too_short():
    audio_b64 = base64.b64encode(b"\x00" * 100).decode()
    req = _make_request({"audio_base64": audio_b64, "patient_id": "q1b"})
    response = await api_whatsapp_voice(req)
    assert response.status_code == 400
    data = json.loads(response.body)
    assert "too short" in data["error"]


# ── Audio too large ───────────────────────────────────


@pytest.mark.anyio
async def test_voice_endpoint_audio_too_large():
    # 10.1MB raw → base64 is ~13.5MB, under 15MB JSON limit but over 10MB binary
    audio_b64 = base64.b64encode(b"\x00" * (10 * 1024 * 1024 + 1)).decode()
    req = _make_request({"audio_base64": audio_b64, "patient_id": "q1b"})
    response = await api_whatsapp_voice(req)
    assert response.status_code == 400
    data = json.loads(response.body)
    assert "too large" in data["error"]


# ── Transcription error → 503 ─────────────────────────


@pytest.mark.anyio
@patch(
    "oncoteam.whisper_client.transcribe_audio",
    new_callable=AsyncMock,
)
async def test_voice_endpoint_transcription_error(mock_transcribe):
    mock_transcribe.return_value = {"error": "Whisper circuit breaker open"}
    audio_b64 = base64.b64encode(b"\x00" * 2000).decode()
    req = _make_request(
        {"audio_base64": audio_b64, "content_type": "audio/ogg", "patient_id": "q1b"}
    )
    response = await api_whatsapp_voice(req)
    assert response.status_code == 503
    data = json.loads(response.body)
    assert "error" in data
