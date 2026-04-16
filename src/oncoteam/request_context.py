"""Request-scoped context utilities.

Extracted from dashboard_api.py to break circular imports with
oncofiles_client.py and autonomous.py.
"""

from __future__ import annotations

import contextvars
import uuid

from .patient_context import get_patient_token

# ── Request correlation ID ─────────────────────────────────────────────
# Short UUID generated per API request for log correlation.
_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("_CORRELATION_ID", default="")


def new_correlation_id() -> str:
    """Generate a short correlation ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def get_correlation_id() -> str:
    """Return current request's correlation ID (empty if none)."""
    return _CORRELATION_ID.get()


def set_correlation_id(cid: str) -> None:
    """Set the current request's correlation ID."""
    _CORRELATION_ID.set(cid)


# ── Patient token resolution ──────────────────────────────────────────


def get_token_for_patient(patient_id: str) -> str | None:
    """Get the oncofiles bearer token for a patient. None = default (Erika)."""
    if not patient_id or patient_id == "q1b":
        return None  # Use default ONCOFILES_MCP_TOKEN
    return get_patient_token(patient_id)
