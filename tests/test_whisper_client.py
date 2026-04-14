"""Tests for whisper_client.py — OpenAI Whisper transcription + circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oncoteam import whisper_client


@pytest.fixture(autouse=True)
def _reset_whisper_state():
    """Reset circuit breaker and stats between tests."""
    whisper_client._cb_failures = 0
    whisper_client._cb_open_until = 0.0
    whisper_client._stats = {
        "calls": 0,
        "errors": 0,
        "cost_usd": 0.0,
        "total_duration_s": 0.0,
        "total_latency_ms": 0,
    }
    yield


def _mock_config(api_key="sk-test-key"):
    """Patch config values used by whisper_client via lazy import."""
    return (
        patch("oncoteam.config.OPENAI_API_KEY", api_key),
        patch("oncoteam.config.WHISPER_MODEL", "whisper-1"),
        patch("oncoteam.config.WHISPER_TIMEOUT", 30),
    )


# ── Successful transcription ──────────────────────────


@pytest.mark.anyio
async def test_transcribe_audio_success():
    mock_response = MagicMock()
    mock_response.text = "labky cea"
    mock_response.duration = 5.2

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    p1, p2, p3 = _mock_config()
    with (
        p1,
        p2,
        p3,
        patch("openai.AsyncOpenAI", return_value=mock_client),
        patch("oncoteam.whisper_client._track_whisper_cost"),
    ):
        result = await whisper_client.transcribe_audio(
            audio_bytes=b"\x00" * 2000,
            content_type="audio/ogg; codecs=opus",
            patient_id="q1b",
            lang_hint="sk",
        )

    assert result["text"] == "labky cea"
    assert result["duration_s"] == 5.2
    assert result["cost"] > 0
    assert result["lang"] == "sk"
    assert whisper_client._stats["calls"] == 1
    assert whisper_client._stats["errors"] == 0


# ── Missing API key ──────────────────────────────────


@pytest.mark.anyio
async def test_transcribe_audio_no_api_key():
    p1, p2, p3 = _mock_config(api_key="")
    with p1, p2, p3:
        result = await whisper_client.transcribe_audio(b"\x00" * 2000)
    assert "error" in result
    assert "not configured" in result["error"]


# ── API failure + circuit breaker ─────────────────────


@pytest.mark.anyio
async def test_transcribe_audio_api_failure():
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=RuntimeError("API error")
    )

    p1, p2, p3 = _mock_config()
    with p1, p2, p3, patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await whisper_client.transcribe_audio(b"\x00" * 2000)

    assert "error" in result
    assert whisper_client._stats["errors"] == 1
    assert whisper_client._cb_failures == 1


@pytest.mark.anyio
async def test_circuit_breaker_opens_after_threshold():
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=RuntimeError("API error")
    )

    p1, p2, p3 = _mock_config()
    with p1, p2, p3, patch("openai.AsyncOpenAI", return_value=mock_client):
        for _ in range(3):
            await whisper_client.transcribe_audio(b"\x00" * 2000)

    assert whisper_client._cb_failures == 3
    assert whisper_client._cb_is_open() is True

    # Next call should fail immediately (CB checked before config import)
    result = await whisper_client.transcribe_audio(b"\x00" * 2000)
    assert "circuit breaker" in result["error"].lower()


def test_circuit_breaker_resets_after_cooldown():
    whisper_client._cb_failures = 3
    whisper_client._cb_open_until = time.monotonic() - 1  # expired
    assert whisper_client._cb_is_open() is False


# ── Content type normalization ────────────────────────


@pytest.mark.anyio
async def test_content_type_codec_stripped():
    """audio/ogg; codecs=opus -> file extension .ogg"""
    mock_response = MagicMock()
    mock_response.text = "hello"
    mock_response.duration = 1.0

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    p1, p2, p3 = _mock_config()
    with (
        p1,
        p2,
        p3,
        patch("openai.AsyncOpenAI", return_value=mock_client),
        patch("oncoteam.whisper_client._track_whisper_cost"),
    ):
        result = await whisper_client.transcribe_audio(
            audio_bytes=b"\x00" * 2000,
            content_type="audio/ogg; codecs=opus",
        )

    assert result["text"] == "hello"
    # Verify the file was created with .ogg extension
    call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
    assert call_kwargs["file"].name == "voice.ogg"


# ── Stats ─────────────────────────────────────────────


def test_get_whisper_stats():
    whisper_client._stats["calls"] = 5
    whisper_client._stats["cost_usd"] = 0.03
    stats = whisper_client.get_whisper_stats()
    assert stats["calls"] == 5
    assert stats["cost_usd"] == 0.03
    assert stats["circuit_breaker"] == "closed"


def test_get_whisper_stats_with_open_cb():
    whisper_client._cb_open_until = time.monotonic() + 60
    stats = whisper_client.get_whisper_stats()
    assert stats["circuit_breaker"] == "open"
