"""OpenAI Whisper API client for WhatsApp voice note transcription.

Ephemeral audio: bytes are never stored — download, transcribe, discard.
Circuit breaker: 3 consecutive failures → 60s cooldown.
Cost: $0.006/min → tracked via autonomous._track_cost pattern.
"""

from __future__ import annotations

import io
import logging
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker (lightweight — single external API)
# ---------------------------------------------------------------------------
_CB_THRESHOLD = 3
_CB_COOLDOWN_S = 60
_cb_failures = 0
_cb_open_until = 0.0


def _cb_record_success() -> None:
    global _cb_failures
    _cb_failures = 0


def _cb_record_failure() -> None:
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= _CB_THRESHOLD:
        _cb_open_until = time.monotonic() + _CB_COOLDOWN_S
        logger.warning("Whisper circuit breaker OPEN for %ds", _CB_COOLDOWN_S)


def _cb_is_open() -> bool:
    if _cb_open_until == 0.0:
        return False
    # Half-open: allow one attempt after cooldown expires
    return time.monotonic() < _cb_open_until


# ---------------------------------------------------------------------------
# Stats (in-memory, exposed via /api/diagnostics)
# ---------------------------------------------------------------------------
_stats: dict[str, float] = {
    "calls": 0,
    "errors": 0,
    "cost_usd": 0.0,
    "total_duration_s": 0.0,
    "total_latency_ms": 0,
}


def get_whisper_stats() -> dict:
    """Return current session stats for diagnostics."""
    return {
        **_stats,
        "circuit_breaker": "open" if _cb_is_open() else "closed",
        "cb_failures": _cb_failures,
    }


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
async def transcribe_audio(
    audio_bytes: bytes,
    content_type: str = "audio/ogg",
    patient_id: str = "q1b",
    lang_hint: str = "sk",
) -> dict:
    """Transcribe audio bytes via OpenAI Whisper API.

    Returns {"text": str, "duration_s": float, "cost": float, "lang": str}
    or {"error": str} on failure.
    """
    if _cb_is_open():
        return {"error": "Whisper circuit breaker open — temporarily unavailable"}

    from .config import OPENAI_API_KEY, WHISPER_MODEL, WHISPER_TIMEOUT

    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not configured"}

    # Map content type to file extension for Whisper
    ext_map = {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/amr": "amr",
        "audio/wav": "wav",
        "audio/webm": "webm",
    }
    # Normalize: strip codec params (e.g. "audio/ogg; codecs=opus" → "audio/ogg")
    mime_base = content_type.split(";")[0].strip()
    ext = ext_map.get(mime_base, "ogg")

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=WHISPER_TIMEOUT)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"voice.{ext}"

        t0 = time.monotonic()
        response = await client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            language=lang_hint,
            response_format="verbose_json",
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        text = response.text or ""
        duration_s = getattr(response, "duration", 0.0) or 0.0
        cost = (duration_s / 60) * 0.006

        # Track cost via autonomous module
        _track_whisper_cost(cost, patient_id)

        # Update stats
        _stats["calls"] += 1
        _stats["cost_usd"] += cost
        _stats["total_duration_s"] += duration_s
        _stats["total_latency_ms"] += latency_ms

        _cb_record_success()

        logger.info(
            "Whisper transcription: %dms, %.1fs audio, $%.4f, patient=%s, text=%s",
            latency_ms,
            duration_s,
            cost,
            patient_id,
            text[:80],
        )

        return {
            "text": text,
            "duration_s": round(duration_s, 1),
            "cost": round(cost, 6),
            "lang": lang_hint,
        }

    except Exception as e:
        _cb_record_failure()
        _stats["errors"] += 1
        logger.error("Whisper transcription failed: %s", e)
        # Lazy import to avoid circular dependency
        try:
            from .activity_logger import record_suppressed_error

            record_suppressed_error("whisper_client", "transcribe", e)
        except Exception:
            pass
        return {"error": str(e)}


def _track_whisper_cost(cost: float, patient_id: str) -> None:
    """Feed Whisper cost into the autonomous daily cost tracker."""
    try:
        from .autonomous import _daily_cost, _daily_cost_reset_date

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if _daily_cost_reset_date != today:
            # Don't reset here — let autonomous._track_cost handle the reset
            return
        _daily_cost[patient_id] = _daily_cost.get(patient_id, 0.0) + cost
        _daily_cost["global"] = _daily_cost.get("global", 0.0) + cost
    except Exception:
        pass  # Non-critical — cost tracking failure should not break transcription
